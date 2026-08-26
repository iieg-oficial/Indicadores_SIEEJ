"""Resolución del DSN por pipeline y su pool, creado en la primera consulta.

Reemplaza a `core/config.py` y `core/db.py` de ETL-SIEEJ, que no se portan porque
asumen un `core/pipelines/<pipeline>/.env` que aquí no existe.

El campo `pipeline` del YAML es la **clave de conexión**: se conserva el nombre por
compatibilidad con el catálogo del ETL. El orden de resolución y el presupuesto de
conexiones están en docs/conexiones.md.
"""

import os
import threading
from typing import Iterable, Optional

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import SQLAlchemyError

from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import PipelineUnavailable

# Pools abiertos, uno por pipeline. Es un dict y no un lru_cache porque /ready
# necesita saber cuáles están abiertos sin abrir ninguno.
_POOLS: dict[str, Engine] = {}
_LOCK = threading.Lock()


def dsn(pipeline: str, cfg: Optional[Settings] = None) -> Optional[URL | str]:
    """El DSN del pipeline, o None si este despliegue no lo sirve.

    1. `IIEGDB_DSN_<PIPELINE>` si existe: gana siempre.
    2. El servidor por defecto, si el pipeline está habilitado.
    3. Nada.
    """
    cfg = cfg or settings()

    explicit = os.environ.get(f"IIEGDB_DSN_{pipeline.upper()}")
    if explicit:
        return explicit

    if not cfg.serves(pipeline):
        return None

    # URL.create escapa la contraseña por su cuenta: por eso no hace falta
    # URL-encodearla en el .env.
    return URL.create(
        "postgresql",
        username=cfg.pg_user,
        password=cfg.pg_password.get_secret_value(),
        host=cfg.pg_host,
        port=cfg.pg_port,
        database=pipeline,
        query={"sslmode": cfg.pg_sslmode},
    )


def available(pipeline: str, cfg: Optional[Settings] = None) -> bool:
    return dsn(pipeline, cfg) is not None


def pool(pipeline: str, cfg: Optional[Settings] = None) -> Engine:
    """El pool del pipeline. **Se crea aquí, en la primera consulta, no al arrancar.**

    Con 100 pipelines catalogados y 3 en uso se mantienen 3 pools; abrirlos todos al
    arranque rebasaría el `max_connections` del servidor mucho antes de llegar a 100.
    """
    cfg = cfg or settings()

    with _LOCK:
        if pipeline not in _POOLS:
            target = dsn(pipeline, cfg)
            if target is None:
                raise PipelineUnavailable(f"el pipeline '{pipeline}' no tiene DSN en este despliegue")
            _POOLS[pipeline] = create_engine(
                target,
                pool_size=cfg.pool_size,
                max_overflow=cfg.pool_max_overflow,
                pool_timeout=cfg.pool_timeout_s,
                # El servidor es un proceso de larga vida, a diferencia del CLI del ETL.
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={"options": f"-c statement_timeout={cfg.statement_timeout_ms}"},
            )
        return _POOLS[pipeline]


def is_open(pipeline: str) -> bool:
    return pipeline in _POOLS


def status(pipelines: Iterable[str], cfg: Optional[Settings] = None) -> dict[str, dict]:
    """Estado por pipeline para /ready. **No abre pools.**

    Distingue "sin DSN" de "pool sin abrir" porque la acción del operador es distinta
    en cada caso: la primera es configuración, la segunda es que nadie ha consultado.
    """
    cfg = cfg or settings()
    return {
        pipeline: {"dsn": available(pipeline, cfg), "pool": "open" if is_open(pipeline) else "unopened"}
        for pipeline in sorted(set(pipelines))
    }


def check(pipeline: str, cfg: Optional[Settings] = None) -> bool:
    """Verifica de verdad un pipeline: abre su pool y le pide un `SELECT 1`.

    Es lo único que abre un pool sin que nadie haya consultado, y por eso solo lo llama
    `/ready?pipeline=<p>` para uno a la vez: hacerlo con todos convertiría cada sondeo
    del orquestador en una conexión por pipeline catalogado.
    """
    cfg = cfg or settings()
    try:
        with pool(pipeline, cfg).connect() as conn:
            conn.execute(text("SELECT 1"))
    except (SQLAlchemyError, PipelineUnavailable):
        return False
    return True


def close_all() -> None:
    """Cierra los pools abiertos. Para el apagado del servidor y para las pruebas."""
    with _LOCK:
        while _POOLS:
            _, engine = _POOLS.popitem()
            engine.dispose()
