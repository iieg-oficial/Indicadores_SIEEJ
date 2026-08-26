"""El registro de API keys: modelo, conexión de escritura y migraciones.

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

import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import CheckConstraint, DateTime, Engine, Index, String, Text, create_engine, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID as PGUUID
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
    global _ENGINE
    with _LOCK:
        if _ENGINE is not None:
            _ENGINE.dispose()
            _ENGINE = None


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
