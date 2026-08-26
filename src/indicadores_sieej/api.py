"""Las cinco rutas REST de `/v1` más las dos de operación.

El mismo motor que sirve a MCP, con otro transporte. Igual que allá, esta capa no toma
ninguna decisión de negocio: traduce la petición a una llamada al motor y la excepción
al código HTTP que la excepción ya declara.

**La traducción es por tipo, nunca por el texto del mensaje.** Es justamente para eso
que existe la jerarquía de docs/errores.md: inspeccionar cadenas para decidir un código
es lo que no escala con dos superficies.

Las rutas, los nombres de los query params y las claves del sobre van en español porque
son el contrato de docs/superficies.md.
"""

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from indicadores_sieej import connections, engine
from indicadores_sieej.catalog import find, get, load
from indicadores_sieej.errors import BankError

router = APIRouter(prefix="/v1", tags=["indicadores"])
operations = APIRouter(tags=["operación"])


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
    """Liveness. **Es la única ruta que responde sin autenticación.**"""
    return {"status": "ok"}


@operations.get("/ready")
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
