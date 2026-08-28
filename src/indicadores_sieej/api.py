"""Las rutas REST de `/v1` más las dos de operación.

El mismo motor que sirve a MCP, con otro transporte. Igual que allá, esta capa no toma
ninguna decisión de negocio: traduce la petición a una llamada al motor y la excepción
al código HTTP que la excepción ya declara.

**La traducción es por tipo, nunca por el texto del mensaje.** Es justamente para eso
que existe la jerarquía de docs/errores.md: inspeccionar cadenas para decidir un código
es lo que no escala con dos superficies.

Las rutas, los nombres de los query params y las claves del sobre van en español porque
son el contrato de docs/superficies.md.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastmcp.server.auth.auth import AccessToken
from pydantic import BaseModel, ConfigDict, EmailStr

from indicadores_sieej import connections, engine, limits, registry
from indicadores_sieej.auth import ApiKeyVerifier, authenticated, verifier
from indicadores_sieej.catalog import find, get, load
from indicadores_sieej.errors import BankError, RegistryUnavailable

# La dependencia va en el router y no ruta por ruta: así una ruta nueva nace protegida
# en vez de nacer abierta y esperar a que alguien se acuerde.
AUTH = [Depends(authenticated)]

router = APIRouter(prefix="/v1", tags=["indicadores"], dependencies=AUTH)
operations = APIRouter(tags=["operación"])
schema = APIRouter(tags=["operación"], dependencies=AUTH, include_in_schema=False)

# El tercer router existe por una sola ruta, y no por gusto de simetría: `POST
# /v1/api-keys` no puede vivir en el de arriba porque las `dependencies` de un router
# **no se anulan por ruta**, ni con `dependencies=[]`. Está verificado.
public = APIRouter(prefix="/v1", tags=["api keys"])


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Un cuerpo o un parámetro inválido es **400**, no el 422 que FastAPI trae de fábrica.

    docs/errores.md ya asigna el 400 a los parámetros inválidos y el motor lo usa para los
    del indicador; dejar que la única ruta con cuerpo respondiera 422 partiría esa tabla en
    dos por un detalle del framework.

    Sale el **nombre del campo, nunca el valor**: el detalle de pydantic repite lo recibido,
    y en la ruta de emisión eso sería un correo en el cuerpo de una respuesta de error.
    """
    fields = sorted({str(error["loc"][-1]) for error in exc.errors() if error.get("loc")})
    return JSONResponse(status_code=400, content={"detail": f"petición inválida: {fields}"})


async def bank_error_handler(request: Request, exc: BankError) -> JSONResponse:
    """Cada excepción del banco sale con el código que ella misma declara.

    El texto viaja íntegro: en los recuperables es lo que permite al cliente reintentar
    bien, y los no recuperables ya vienen redactados sin sql, sin DSN y sin trazas.
    """
    return JSONResponse(status_code=exc.http, content={"detail": str(exc)})


@router.get("/indicadores")
def list_indicators(tema: Optional[str] = None, nivel: Optional[str] = None) -> list[dict]:
    """Lista los indicadores del catálogo, filtrables por tema y por nivel.

    Devuelve la vista reducida —id, nombre, tema, nivel, unidad y periodicidad—; la
    metadata completa de uno se pide en `/v1/indicadores/{id}`. Sin coincidencias
    devuelve una lista vacía, no un 404.
    """
    return find(tema=tema, nivel=nivel)


@router.get("/indicadores/{id}")
def describe_indicator(id: str) -> dict:
    """Metadata completa del indicador, **sin** el campo `sql`.

    `parametros[]` es lo que hay que leer antes de pedir datos: nombre, tipo y si es
    requerido cada valor que acepta la ruta `/datos`.
    """
    return get(id).metadata()


@router.get("/indicadores/{id}/datos")
def query_indicator(id: str, request: Request) -> dict:
    """Datos del indicador, con su metadata al lado.

    Los parámetros viajan como query params con **el mismo nombre** que declara el YAML
    del indicador, así que no se pueden enumerar aquí: se toman tal cual del query
    string y los valida el motor contra los declarados. Uno no declarado devuelve
    `400`; ignorarlo en silencio haría que el cliente creyera que su filtro se aplicó.
    """
    return engine.execute(id, dict(request.query_params))


@operations.get("/health")
def health() -> dict:
    """Liveness. **Es la única ruta que responde sin autenticación.**

    Reporta además el último estado observado del registro de API keys. Sin eso, un
    registro caído deja al operador a ciegas: `/ready` exige credencial, y con el registro
    abajo devuelve 503 antes de llegar al handler — indistinguible de «todo caído».

    Dos cosas que no se negocian aquí. **No abre ninguna conexión**: es la única ruta
    anónima, y sondear la base desde ella la volvería un amplificador de DoS. Y **sigue
    respondiendo 200 siempre**: es liveness de *este proceso*, y devolver 503 porque el
    registro parpadeó haría que el orquestador reinicie un servidor sano.
    """
    return {"status": "ok", "registro": registry.state()}


@operations.get("/ready", dependencies=AUTH)
def ready(pipeline: Optional[str] = None) -> JSONResponse:
    """Readiness por pipeline: si tiene DSN resuelto y si su pool está abierto.

    **No abre pools.** Reportar el DSN de todos y el estado solo de los ya abiertos es
    lo que evita que cada sondeo del orquestador cueste una conexión por pipeline
    catalogado. `?pipeline=<p>` fuerza la verificación real de uno solo.
    """
    if pipeline is not None:
        responds = connections.check(pipeline)
        payload = {"pipeline": pipeline, "dsn": connections.available(pipeline), "responds": responds}
        return JSONResponse(status_code=200 if responds else 503, content=payload)

    pipelines = connections.status({ind.pipeline for ind in load().values()})
    # Que algunos pipelines no tengan DSN es un despliegue parcial legítimo: sus
    # indicadores responden 503 uno por uno. Sin ninguno, el servidor no sirve nada.
    is_ready = any(state["dsn"] for state in pipelines.values())
    return JSONResponse(status_code=200 if is_ready else 503, content={"ready": is_ready, "pipelines": pipelines})


# --- API keys: el autoservicio ------------------------------------------------------
#
# Las tres rutas se registran en **los tres modos de auth**. Condicionarlas a la
# configuración haría que el conjunto fijo de rutas —el canario que verifica que ninguna
# nazca abierta— dependiera del entorno. Fuera del modo `api_key` responden 503.


class ApiKeyRequest(BaseModel):
    """El cuerpo de la emisión: un correo y nada más.

    `extra="forbid"` no es rigor de estilo. Sin él, un `scopes` en el cuerpo de una
    petición **pública y sin autenticar** sería escalada de privilegios, y es exactamente
    el campo que alguien va a querer agregar "por flexibilidad". Los scopes los pone el
    servidor, y ninguna ruta los acepta de fuera.
    """

    model_config = ConfigDict(extra="forbid")

    correo: EmailStr


def api_key_verifier() -> ApiKeyVerifier:
    """El verificador del proceso, si este despliegue emite API keys.

    Devolver el verificador y no el almacén a secas es lo que permite a `DELETE` revocar
    **y** desalojar el caché en el mismo lugar: sin lo segundo, la key propia seguiría
    sirviendo hasta que expirara su entrada.
    """
    current = verifier()
    if not isinstance(current, ApiKeyVerifier):
        raise RegistryUnavailable("el registro de API keys no está disponible en este despliegue")
    return current


def issue_allowed(request: Request) -> None:
    """El límite por IP sobre la emisión. Va como dependencia y no dentro del handler
    porque así se aplica **antes** de validar el cuerpo, y no solo a los bien formados.

    La IP sale de `request.client.host` y **no** de `X-Forwarded-For`: confiar en esa
    cabecera haría el límite evadible con un encabezado. Detrás de un proxy inverso, quien
    la vuelve real es `uvicorn --proxy-headers --forwarded-allow-ips=<proxy>` — ver
    docs/configuracion.md.
    """
    limits.issue_limiter().check(request.client.host if request.client else "desconocida")


@public.post("/api-keys", status_code=201, dependencies=[Depends(issue_allowed)])
def issue_api_key(body: ApiKeyRequest, response: Response) -> dict:
    """Emite una API key para un correo. **La segunda ruta que responde sin credencial.**

    La key viaja en la respuesta y **solo ahí**: no se guarda en claro y no se puede
    recuperar. Pedir otra para el mismo correo revoca la anterior — es la rotación, y
    también la vía de recuperación de quien perdió la suya.

    El correo se normaliza antes de guardarse; la base rechaza el bypass con un `CHECK`.
    """
    key, stored = api_key_verifier().store.issue(body.correo.strip().lower())
    # La key en claro no puede quedarse en un caché intermedio ni en el del navegador.
    response.headers["Cache-Control"] = "no-store"
    return {"api_key": key, "correo": stored.correo, "expira_en": _iso(stored.expires_at)}


@router.get("/api-keys/actual", dependencies=[Depends(api_key_verifier)])
def current_api_key(access: AccessToken = Depends(authenticated)) -> dict:
    """Qué es la credencial con la que se está preguntando.

    **No devuelve la key ni su hash**, y **no toca la base**: todo sale del `AccessToken`
    que el verificador ya armó. La dependencia de arriba está por el 503 fuera del modo
    `api_key`, no porque haga falta el registro.
    """
    claims = access.claims
    return {
        "correo": claims["correo"],
        "prefijo": claims["prefijo"],
        "scopes": list(access.scopes or []),
        "emitida_en": claims["created_at"],
        "ultimo_uso": claims["last_used_at"],
        "expira_en": _iso(access.expires_at),
    }


@router.delete("/api-keys/actual", status_code=204)
def revoke_api_key(
    access: AccessToken = Depends(authenticated),
    current: ApiKeyVerifier = Depends(api_key_verifier),
) -> Response:
    """Revoca la key con la que se está preguntando. Solo la propia: la identidad sale del
    `AccessToken`, no del cuerpo.

    Se desaloja además del caché de **este** proceso para que sea inmediata aquí. En los
    demás workers tarda lo que dure su entrada — ver docs/api-keys.md.
    """
    current.store.revoke(UUID(access.client_id))
    current.forget(access.token)
    return Response(status_code=204)


def _iso(epoch: Optional[int]) -> Optional[str]:
    """Un epoch de la base como marca de tiempo UTC, que es lo que el cliente entiende."""
    if epoch is None:
        return None
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat().replace("+00:00", "Z")


# El esquema se publica autenticado, como todo salvo /health: `docs/garantias.md` no
# hace excepción para él. Por eso se apagan los de FastAPI y se re-registran aquí.


@schema.get("/openapi.json")
def openapi_schema(request: Request) -> dict:
    """El OpenAPI del servidor."""
    return request.app.openapi()


@schema.get("/docs", response_class=HTMLResponse)
def swagger_ui() -> HTMLResponse:
    """La consola de OpenAPI."""
    return get_swagger_ui_html(openapi_url="/openapi.json", title="Banco de indicadores IIEG")
