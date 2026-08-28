"""El registro de API keys: modelo, migraciones, conexión de escritura y su almacén.

**Es la única ruta de escritura del proyecto.** Todo lo demás lee: el catálogo del disco,
la configuración del entorno y las 33 bases del ETL. Sobre esas últimas se sigue sin
escribir jamás — lo que se estrena aquí es una base de este servicio, para su propio
estado operativo.

Va en un módulo aparte de `connections.py` por dos razones que no son estéticas:

- Los pools de allá son de **solo lectura** y se resuelven por pipeline; este es de
  escritura y no tiene pipeline.
- `/ready` recorre `connections._POOLS` y lo mapea contra los pipelines del catálogo. Si
  el motor del registro entrara ahí, aparecería como un pipeline inexistente.

El DSN es su propia variable y **nunca** se deriva de `IIEGDB_PG_*`: ese bloque es el rol
de solo lectura, y derivar de ahí crearía presión para concederle escritura, lo que
rompería la garantía de solo lectura en las 33 bases a la vez.
"""

import hashlib
import logging
import secrets
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Protocol
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, DateTime, Engine, Index, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import RegistryUnavailable

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = ROOT / "alembic.ini"

# Los nombres de columna van en español y los de auditoría en inglés: es la convención
# de ETL-SIEEJ, y esta base se opera junto a las suyas.


class Base(DeclarativeBase):
    pass


class ApiKey(Base):
    """Una API key emitida. La key en claro no está aquí: solo su sha256.

    Los `comment=` no son documentación de cortesía — SQLAlchemy los emite como
    `COMMENT ON`, y son la única descripción que tiene un operador frente a un `psql`
    sin este repositorio a la mano. Es la norma más fuerte de ETL-SIEEJ.
    """

    __tablename__ = "api_keys"
    __table_args__ = (
        # Sin normalizar, `A@b.mx` y `a@b.mx` son filas distintas y el índice de abajo
        # deja de significar "una API key por cuenta". Se normaliza al escribir y la base
        # rechaza el bypass.
        CheckConstraint("correo = lower(btrim(correo))", name="ck_api_keys_correo_normalizado"),
        # Esto es lo que **realmente** impone una API key activa por correo. Ordenar el
        # UPDATE antes del INSERT no basta: bajo READ COMMITTED la segunda transacción se
        # desbloquea, ve la fila ya revocada, actualiza cero filas e inserta igual.
        Index(
            "uq_api_keys_correo_activo",
            "correo",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        {"comment": "API keys de acceso al banco de indicadores, emitidas por autoservicio en POST /v1/api-keys."},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        # Del núcleo desde PostgreSQL 13: no hace falta pgcrypto, que exigiría superusuario.
        server_default=text("gen_random_uuid()"),
        comment="Identidad del consumidor. Es lo que viaja a la auditoría, no el correo, que es dato personal.",
    )
    correo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment=(
            "Correo del solicitante, normalizado a minúsculas y sin espacios. "
            "Hoy solo es clave de unicidad: no está verificado."
        ),
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        comment="sha256 hexadecimal de la API key. La key en claro no se almacena en ninguna parte.",
    )
    prefijo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Primeros caracteres de la API key, sin valor secreto. Permite identificarla en soporte sin conocerla.",
    )
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default=text("ARRAY['indicadores:read']"),
        comment="Permisos de la API key. Los asigna el servidor; nunca se aceptan desde la petición.",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment="Cuándo se emitió.",
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        comment=(
            "Última verificación exitosa. Se refresca de forma acotada, no en cada petición, "
            "y es contra esto que se mide la caducidad por desuso."
        ),
    )
    revoked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        comment="Cuándo se revocó, o NULL si sigue activa. Rotar para el mismo correo revoca la anterior.",
    )


_ENGINE: Optional[Engine] = None
_LOCK = threading.Lock()

# El último estado observado del registro, para que `/health` lo reporte. Es un
# resultado del tráfico real, no una sonda: ver `state()`.
OK = "ok"
DOWN = "caido"
UNKNOWN = "desconocido"
NOT_APPLICABLE = "no_aplica"

_STATE = UNKNOWN


def dsn(cfg: Optional[Settings] = None) -> str:
    """El DSN del registro. Falla ruidoso si el despliegue no lo configuró."""
    cfg = cfg or settings()
    if not cfg.registry_dsn:
        raise RegistryUnavailable("el registro de API keys no está configurado en este despliegue")
    return cfg.registry_dsn.get_secret_value()


def engine(cfg: Optional[Settings] = None) -> Engine:
    """El motor del registro, creado en el primer uso.

    Pool pequeño a propósito: el registro atiende una consulta corta por verificación
    que falla el caché, no cargas de datos.
    """
    global _ENGINE
    cfg = cfg or settings()

    with _LOCK:
        if _ENGINE is None:
            _ENGINE = create_engine(
                dsn(cfg),
                pool_size=1,
                max_overflow=2,
                pool_timeout=cfg.pool_timeout_s,
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={"options": f"-c statement_timeout={cfg.statement_timeout_ms}"},
            )
        return _ENGINE


def close() -> None:
    """Cierra el motor. Para el apagado del servidor y para las pruebas."""
    global _ENGINE, _STATE
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.dispose()
            _ENGINE = None
        _STATE = UNKNOWN


def state(cfg: Optional[Settings] = None) -> str:
    """Lo último que se supo del registro: `ok`, `caido`, `desconocido` o `no_aplica`.

    Es el resultado del **tráfico real**, no de una sonda, y esa es la decisión: `/health`
    es la única ruta anónima del servidor, así que sondear la base desde ella la
    convertiría en un amplificador de DoS. A cambio, un servidor recién arrancado dice
    `desconocido` hasta que alguien se autentique, que es lo honesto.
    """
    cfg = cfg or settings()
    return _STATE if cfg.auth_mode == "api_key" else NOT_APPLICABLE


def alembic_config(cfg: Optional[Settings] = None) -> Config:
    """La configuración de Alembic, con el DSN inyectado desde las settings.

    `alembic.ini` **no lleva el DSN**: lleva credenciales, y ese archivo se versiona.
    Pasarlo por aquí deja una sola fuente de verdad —`IIEGDB_REGISTRY_DSN`— para el
    servidor y para las migraciones.
    """
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", dsn(cfg))
    return config


def migrate(cfg: Optional[Settings] = None) -> None:
    """Lleva el registro a la última revisión.

    **No corre al arrancar el servidor**, y es deliberado: es la convención de ETL-SIEEJ,
    y mantenerla significa que el rol del servidor no necesita permisos de DDL en
    operación normal.
    """
    command.upgrade(alembic_config(cfg), "head")


# --- El almacén ---------------------------------------------------------------------
#
# El verificador depende del **protocolo, no de SQLAlchemy**. Es lo que permite ejercitar
# todo el recorrido en CI sin una base viva, con el doble en memoria de tests/conftest.py
# — el mismo patrón que `_Connection`/`_Pool` usa para el motor de consultas.

PREFIX = "iieg_"
# Lo que se guarda como prefijo: el marcador más ocho caracteres. Suficiente para
# distinguir dos keys en un ticket, muy lejos de reconstruir 256 bits.
PREFIX_LEN = len(PREFIX) + 8


def hashed(key: str) -> str:
    """El sha256 hexadecimal de una API key.

    Sin sal, a propósito: es lo que permite buscar por índice con `WHERE key_hash = :h`.
    Y sin bcrypt: la key son 256 bits aleatorios, no una contraseña humana, y este hash
    está en el camino caliente de cada petición. El razonamiento largo, en docs/api-keys.md.
    """
    return hashlib.sha256(key.encode()).hexdigest()


def new_key() -> tuple[str, str, str]:
    """Una API key nueva: `(key en claro, sha256, prefijo)`.

    El prefijo `iieg_` no es decorativo: la hace reconocible para un escáner de secretos
    y permite nombrarla en soporte sin que nadie pegue la credencial completa.
    """
    key = PREFIX + secrets.token_urlsafe(32)
    return key, hashed(key), key[:PREFIX_LEN]


@dataclass(frozen=True)
class StoredKey:
    """Una fila del registro, ya sin nada secreto.

    `expires_at` e `idle_s` los calcula **el servidor de base de datos**: la caducidad se
    mide contra `now()` de allá, nunca contra el reloj de Python. Con un solo reloj, el
    desfase ni siquiera es representable.

    `idle_s` —cuánto lleva sin usarse la key en el momento de leerla— es lo que permite al
    verificador decidir el refresco acotado sin volver a preguntar la hora a la base.
    """

    id: UUID
    correo: str
    prefijo: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime
    expires_at: int
    idle_s: int


class ApiKeyStore(Protocol):
    """Lo que el verificador y las rutas necesitan del registro, y nada más.

    Las cuatro operaciones levantan `RegistryUnavailable` si el registro no responde —
    envolviéndose en `unavailable_on_failure()`, que además anota el estado de `/health`.
    **Nunca devuelven None por una caída**: `find` devuelve None solo cuando la key no
    sirve, que es lo que se traduce a 401.
    """

    def find(self, key_hash: str) -> Optional[StoredKey]: ...

    def touch(self, id: UUID, throttle_s: int) -> None: ...

    def issue(self, correo: str) -> tuple[str, StoredKey]: ...

    def revoke(self, id: UUID) -> None: ...


# Una consulta, un viaje. Que la fila no exista es indistinguible de revocada o de
# caducada por desuso — que es exactamente lo que queremos para el 401.
_COLUMNS = """
    id, correo, prefijo, scopes, created_at, last_used_at,
    EXTRACT(EPOCH FROM (last_used_at + make_interval(days => :ttl_days)))::bigint AS expires_at,
    EXTRACT(EPOCH FROM (now() - last_used_at))::bigint AS idle_s
"""

_FIND = text(f"""
    SELECT {_COLUMNS}
      FROM api_keys
     WHERE key_hash = :key_hash
       AND revoked_at IS NULL
       AND last_used_at > now() - make_interval(days => :ttl_days)
""")

# Idempotente y sin lectura previa, así que dos workers no se estorban: el que llega
# tarde actualiza cero filas y no pasa nada.
_TOUCH = text("""
    UPDATE api_keys
       SET last_used_at = now()
     WHERE id = :id AND last_used_at < now() - make_interval(secs => :throttle_s)
""")

_REVOKE_ACTIVE_FOR = text("UPDATE api_keys SET revoked_at = now() WHERE correo = :correo AND revoked_at IS NULL")

_INSERT = text(f"""
    INSERT INTO api_keys (correo, key_hash, prefijo)
         VALUES (:correo, :key_hash, :prefijo)
      RETURNING {_COLUMNS}
""")

_REVOKE = text("UPDATE api_keys SET revoked_at = now() WHERE id = :id AND revoked_at IS NULL")

# `make_interval` es de core PostgreSQL: evita depender de cómo el driver adapta un
# `timedelta`, que es la clase de detalle que cambia al cambiar de driver.


def _stored(row) -> StoredKey:
    return StoredKey(
        id=UUID(str(row["id"])),
        correo=row["correo"],
        prefijo=row["prefijo"],
        scopes=list(row["scopes"]),
        created_at=row["created_at"],
        last_used_at=row["last_used_at"],
        expires_at=int(row["expires_at"]),
        idle_s=int(row["idle_s"]),
    )


class PostgresApiKeyStore:
    """El registro de verdad. Construirlo **no** conecta: `engine()` es perezoso."""

    def __init__(self, cfg: Optional[Settings] = None) -> None:
        self._cfg = cfg

    @property
    def cfg(self) -> Settings:
        return self._cfg or settings()

    def find(self, key_hash: str) -> Optional[StoredKey]:
        with self._connect() as conn:
            row = conn.execute(_FIND, {"key_hash": key_hash, "ttl_days": self.cfg.api_key_ttl_days}).mappings().first()
        return _stored(row) if row else None

    def touch(self, id: UUID, throttle_s: int) -> None:
        with self._begin() as conn:
            conn.execute(_TOUCH, {"id": str(id), "throttle_s": throttle_s})

    def issue(self, correo: str) -> tuple[str, StoredKey]:
        """Revoca la activa del correo y emite otra. Es la rotación, en una transacción."""
        try:
            return self._issue(correo)
        except IntegrityError:
            # Perdió la carrera contra otra emisión para el mismo correo y el índice
            # parcial la rechazó. Reintentar una vez revoca la fila del ganador e inserta
            # la propia: sigue quedando exactamente una activa, que es la garantía.
            return self._issue(correo)

    def revoke(self, id: UUID) -> None:
        with self._begin() as conn:
            conn.execute(_REVOKE, {"id": str(id)})

    def _issue(self, correo: str) -> tuple[str, StoredKey]:
        key, key_hash, prefijo = new_key()
        # `scopes` no se manda: lo pone el `server_default` de la columna. Es
        # literalmente el servidor asignándolos, y no hay ruta por la que un valor de la
        # petición llegue hasta aquí.
        binds = {
            "correo": correo,
            "key_hash": key_hash,
            "prefijo": prefijo,
            "ttl_days": self.cfg.api_key_ttl_days,
        }
        with self._begin() as conn:
            conn.execute(_REVOKE_ACTIVE_FOR, {"correo": correo})
            row = conn.execute(_INSERT, binds).mappings().one()
            stored = _stored(row)
        return key, stored

    @contextmanager
    def _connect(self):
        with unavailable_on_failure():
            with engine(self._cfg).connect() as conn:
                yield conn

    @contextmanager
    def _begin(self):
        with unavailable_on_failure():
            with engine(self._cfg).begin() as conn:
                yield conn


@contextmanager
def unavailable_on_failure():
    """Traduce cualquier fallo del registro a `RegistryUnavailable`, que es **503**, y
    de paso anota el estado que `/health` reporta.

    Es público porque **toda** implementación de `ApiKeyStore` debe envolverse en él: es
    lo que hace que la traducción, el log y el estado observado sean uno solo y no tres
    copias que se desincronizan.

    La traducción vive aquí y no en el verificador para que las rutas de emisión hereden
    el mismo comportamiento sin repetirlo. `IntegrityError` se deja pasar: no es el
    registro caído, es la carrera de emisión, y `issue` sabe qué hacer con ella.
    """
    global _STATE
    try:
        yield
    except IntegrityError:
        # La base respondió; quien rechazó fue el índice. Como estado del registro, eso
        # es un `ok`.
        _STATE = OK
        raise
    except SQLAlchemyError as exc:
        _STATE = DOWN
        # El detalle va al log, nunca al cliente: un DSN o un nombre de tabla en la
        # respuesta es justo lo que docs/garantias.md no permite salir.
        log.warning("el registro de API keys no respondió: %s", type(exc).__name__)
        raise RegistryUnavailable("el registro de API keys no está disponible") from exc
    _STATE = OK
