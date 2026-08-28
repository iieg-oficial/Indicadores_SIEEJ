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

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Optional
from uuid import UUID

import anyio.to_thread
from fastapi import Request
from fastmcp.server.auth.auth import AccessToken, TokenVerifier
from fastmcp.server.auth.providers.jwt import JWTVerifier, StaticTokenVerifier
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import BankError, InsufficientScope, Unauthenticated
from indicadores_sieej.registry import ApiKeyStore, PostgresApiKeyStore, StoredKey, hashed

log = logging.getLogger(__name__)

# El único scope del banco. Todo lo que no sea /health lo exige.
SCOPE = "indicadores:read"

DAY_S = 86400


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


@dataclass
class _Cached:
    """Una verificación exitosa, guardada para no consultar el registro en cada petición.

    Los tres tiempos van en el **reloj monótono del proceso**; el de la base solo entra
    por `idle_s`, que es lo que fija el punto de partida. Mezclar los dos relojes sería
    justo el error que la caducidad medida en la base evita.
    """

    access: AccessToken
    id: UUID
    # Hasta cuándo se sirve sin volver a preguntar.
    fresh_until: float
    # Cuándo caduca la key misma. La entrada **nunca** lo sobrevive.
    dead_at: float
    # Cuándo se sabe refrescado `last_used_at` en la base.
    touched_at: float


class ApiKeyVerifier(TokenVerifier):
    """Verifica una API key contra el registro. Es el modo de producción, decidido en #29.

    Se construye **sin** `required_scopes`, como los otros dos: el scope lo revisa
    `identify` para poder responder 403 en vez de 401.

    Depende de `ApiKeyStore`, no de SQLAlchemy: es lo que permite ejercitar todo el
    recorrido en CI sin una base viva. `clock` se inyecta por la misma razón — con él, la
    prueba de una key usada cada 30 s durante cien días corre en milisegundos.
    """

    def __init__(
        self,
        store: ApiKeyStore,
        cfg: Settings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(base_url=cfg.base_url)
        self.store = store
        self.cfg = cfg
        self.clock = clock
        # Solo entradas positivas. Cachear el negativo dejaría que un anónimo llene la
        # memoria con hashes inventados: el tamaño quedaría atado a lo que manda el
        # atacante en vez de al número de keys vivas.
        self._cache: dict[str, _Cached] = {}

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        """La API key del `Authorization: Bearer`, o None si no sirve.

        **None significa 401 y solo eso**: key inexistente, revocada o caducada por
        desuso, tres casos indistinguibles a propósito. Un registro que no responde no
        es None, es `RegistryUnavailable` — ver el porqué en errors.py.
        """
        key_hash = hashed(token)
        now = self.clock()

        entry = self._cache.get(key_hash)
        if entry is not None and now < entry.fresh_until:
            await self._touch(entry, now)
            return entry.access

        stored = await self._find(key_hash)
        if stored is None:
            self._cache.pop(key_hash, None)
            return None

        entry = self._remember(key_hash, stored, now)
        await self._touch(entry, now)
        return entry.access

    def forget(self, key_hash: str) -> None:
        """Saca una key del caché de **este** proceso, para que su revocación sea inmediata.

        Recibe el hash porque es lo que `AccessToken.token` ya lleva: quien revoca tiene
        la identidad a la mano y no necesita volver a ver la key. En los demás workers la
        revocación tarda lo que dure su propia entrada — el caché vive en el proceso y no
        hay nada que lo invalide desde fuera.
        """
        self._cache.pop(key_hash, None)

    async def _find(self, key_hash: str) -> Optional[StoredKey]:
        """La consulta al registro, **fuera del event loop**.

        `identify` es `async` y el middleware ASGI de `/mcp` la espera directo, sin la red
        de threadpool que FastAPI tiende bajo los handlers `def`. Una consulta síncrona
        aquí bloquearía el proceso entero en cada fallo de caché, así que el `to_thread`
        no es opcional por más que un `await` sobre una consulta de una línea se vea
        simplificable.
        """
        return await anyio.to_thread.run_sync(self.store.find, key_hash)

    async def _touch(self, entry: _Cached, now: float) -> None:
        """Refresca `last_used_at` si lleva más de `touch_s` sin refrescarse.

        Lo dispara el **uso real**, no el fallo de caché: una key servida desde el caché
        también cuenta como usada, y si no contara, una key muy consultada caducaría por
        desuso. Se hace `await`, no fire-and-forget, pero envuelto: **un refresco fallido
        nunca puede tumbar una autenticación.** Como no se marca `touched_at`, el
        siguiente uso lo reintenta.
        """
        if now - entry.touched_at <= self.cfg.api_key_touch_s:
            return
        try:
            await anyio.to_thread.run_sync(self.store.touch, entry.id, self.cfg.api_key_touch_s)
        except BankError:
            log.warning("no se pudo refrescar el último uso de una API key; la verificación sigue")
            return
        entry.touched_at = now
        entry.dead_at = now + self.cfg.api_key_ttl_days * DAY_S

    def _remember(self, key_hash: str, stored: StoredKey, now: float) -> _Cached:
        """Guarda la verificación. La entrada **nunca vive más que la key**.

        Con eso, la corrección deja de depender del orden de las tres ventanas — que
        config.py valida al arrancar de todos modos.
        """
        dead_at = now + max(self.cfg.api_key_ttl_days * DAY_S - stored.idle_s, 0)
        entry = _Cached(
            access=_access(stored, key_hash),
            id=stored.id,
            fresh_until=min(now + self.cfg.api_key_cache_ttl_s, dead_at),
            dead_at=dead_at,
            # Lo que ya llevaba sin usarse cuando la base la leyó: sin esto, una key que
            # vuelve tras semanas parada no se refrescaría hasta una hora después.
            touched_at=now - stored.idle_s,
        )
        self._cache[key_hash] = entry
        return entry


def _access(stored: StoredKey, key_hash: str) -> AccessToken:
    """La identidad que ven las dos superficies.

    Dos decisiones que no son de estilo:

    - `client_id` y `subject` llevan el **UUID de la fila, no el correo**. Si llevaran el
      correo, cada línea del log de auditoría sería dato personal.
    - `token` lleva el **hash**, no la key en claro. El campo es obligatorio en el modelo
      de FastMCP y el objeto acaba en manos de terceros; con el hash ahí, la key en claro
      no existe en el proceso más allá de la función que la convirtió. `StaticTokenVerifier`
      sí guarda el token, y por eso conviene decir que esto es deliberado.

    `claims` carga lo que `GET /v1/api-keys/actual` devuelve sin volver a tocar la base.
    """
    return AccessToken(
        token=key_hash,
        client_id=str(stored.id),
        subject=str(stored.id),
        scopes=list(stored.scopes),
        expires_at=stored.expires_at,
        claims={
            "correo": stored.correo,
            "prefijo": stored.prefijo,
            "created_at": stored.created_at.isoformat(),
            "last_used_at": stored.last_used_at.isoformat(),
        },
    )


def build_verifier(cfg: Settings) -> TokenVerifier:
    """Arma el verificador que corresponde al modo de autenticación.

    Se construye **sin** `required_scopes`: el scope lo revisa `identify` para poder
    responder `403` en vez de `401`.

    Va separada de `verifier()` porque es la que recibe settings: `Settings` es un modelo
    de pydantic y no es hasheable, así que no puede ser argumento de una función con
    `lru_cache`. Con las dos partidas, esta es pura y probable con cualquier configuración,
    y el caché queda donde no estorba.

    ⚠️ `StaticTokenVerifier` guarda los tokens en texto plano y su propia documentación
    advierte que no se use en producción. Es para desarrollo y pruebas; el modo de
    producción es el que decidió #29 y no pasa por aquí.
    """
    if cfg.auth_mode == "jwt":
        return JWTVerifier(
            jwks_uri=cfg.jwks_uri,
            issuer=cfg.issuer,
            audience=cfg.audience,
            base_url=cfg.base_url,
        )
    if cfg.auth_mode == "api_key":
        # Construirlo no conecta: el motor del registro es perezoso. Un DSN malo se
        # entera en la primera verificación, con un 503 y no con una caída al arrancar.
        return ApiKeyVerifier(PostgresApiKeyStore(cfg), cfg)
    return StaticTokenVerifier(_static_tokens(cfg.static_tokens.get_secret_value()))


@lru_cache(maxsize=1)
def verifier() -> TokenVerifier:
    """El verificador del proceso. **Uno solo**, y las dos superficies lo comparten."""
    return build_verifier(settings())


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
