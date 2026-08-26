"""La verificación de identidad y de scope, **compartida por MCP y REST**.

Dos implementaciones distintas de auth en el mismo proceso es exactamente cómo se abre
un agujero. Aquí hay **una sola función que decide quién entra** —`identify`— y las dos
superficies la llaman: REST como dependencia de FastAPI, MCP como middleware ASGI sobre
su sub-app.

La verificación propia de FastMCP no se conecta: con `required_scopes` colapsa el token
válido-pero-sin-scope en un `401`, y docs/errores.md exige distinguirlo con `403`. Un
`TokenVerifier` pelado tampoco aporta rutas de descubrimiento, así que no se pierde
nada por decidir aquí. Lo que sí se comparte con FastMCP es el verificador: el modo
`jwt` usa su `JWTVerifier` y el `static`, su `StaticTokenVerifier`.
"""

from functools import lru_cache
from typing import Optional

from fastapi import Request
from fastmcp.server.auth.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier, StaticTokenVerifier
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import BankError, InsufficientScope, Unauthenticated

# El único scope del banco. Todo lo que no sea /health lo exige.
SCOPE = "indicadores:read"


def _static_tokens(raw: str) -> dict[str, dict]:
    """Parsea `IIEGDB_STATIC_TOKENS`: `<token>:<cliente>:<scope>[ <scope>…]`, por comas.

    El scope lleva dos puntos dentro, así que se parte en tres y el resto es la lista de
    scopes separados por espacios. **El token no aparece en el mensaje de error**: una
    variable mal escrita no es razón para escribir un secreto en la traza.
    """
    tokens: dict[str, dict] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        try:
            token, client, scopes = entry.split(":", 2)
        except ValueError:
            raise ValueError(
                "IIEGDB_STATIC_TOKENS: cada entrada va como <token>:<cliente>:<scope>, separadas por comas"
            ) from None
        tokens[token] = {"client_id": client, "scopes": scopes.split()}
    return tokens


@lru_cache(maxsize=1)
def verifier(cfg: Optional[Settings] = None) -> TokenVerifier:
    """El verificador del proceso. **Uno solo**, y las dos superficies lo comparten.

    Se construye **sin** `required_scopes`: el scope lo revisa `identify` para poder
    responder `403` en vez de `401`.

    ⚠️ `StaticTokenVerifier` guarda los tokens en texto plano y su propia documentación
    advierte que no se use en producción. Para F1 —despliegue interno, pocos consumidores
    conocidos— es lo que pide SEG-7; **F2 no puede desplegarse así**. #29 decide entre
    pasar a `jwt` o escribir un verificador contra hashes: se cambia esta función, no las
    superficies.
    """
    cfg = cfg or settings()
    if cfg.auth_mode == "jwt":
        return JWTVerifier(
            jwks_uri=cfg.jwks_uri,
            issuer=cfg.issuer,
            audience=cfg.audience,
            base_url=cfg.base_url,
        )
    return StaticTokenVerifier(_static_tokens(cfg.static_tokens.get_secret_value()))


def _bearer(header: Optional[str]) -> Optional[str]:
    """El token de una cabecera `Authorization: Bearer <token>`, o None."""
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def identify(authorization: Optional[str]) -> AccessToken:
    """Quién es y si puede. **El único lugar del proceso donde se decide.**

    Los mensajes no revelan si el token no existe o si solo le falta el scope más allá
    de lo que ya distinguen los dos códigos. Y ninguno lleva el token: no se registra ni
    se devuelve en ningún nivel.
    """
    token = _bearer(authorization)
    if token is None:
        raise Unauthenticated("no autenticado")

    access = await verifier().verify_token(token)
    if access is None:
        raise Unauthenticated("token inválido")

    if SCOPE not in (access.scopes or []):
        raise InsufficientScope(f"el token no tiene el scope '{SCOPE}'")
    return access


async def authenticated(request: Request) -> AccessToken:
    """La dependencia de las rutas REST. Delega en `identify` y no decide nada."""
    return await identify(request.headers.get("authorization"))


class AuthMiddleware:
    """La misma verificación, envuelta como ASGI para la sub-app MCP.

    Es la traducción de transporte de `identify`, no una segunda implementación: si
    alguien cambia la regla, la cambia en un solo lugar y las dos superficies la siguen.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        try:
            await identify(Headers(scope=scope).get("authorization"))
        except BankError as exc:
            response = JSONResponse({"detail": str(exc)}, status_code=exc.http)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
