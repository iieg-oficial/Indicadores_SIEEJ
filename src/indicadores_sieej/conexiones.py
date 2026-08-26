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

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import PipelineUnavailable

# Pools abiertos, uno por pipeline. Es un dict y no un lru_cache porque /ready
# necesita saber cuáles están abiertos sin abrir ninguno.
_POOLS: dict[str, Engine] = {}
_CANDADO = threading.Lock()


def dsn(pipeline: str, cfg: Optional[Settings] = None) -> Optional[URL | str]:
    """El DSN del pipeline, o None si este despliegue no lo sirve.

    1. `IIEGDB_DSN_<PIPELINE>` si existe: gana siempre.
    2. El servidor por defecto, si el pipeline está habilitado.
    3. Nada.
    """
    cfg = cfg or settings()

    propio = os.environ.get(f"IIEGDB_DSN_{pipeline.upper()}")
    if propio:
        return propio

    if not cfg.habilita(pipeline):
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


def disponible(pipeline: str, cfg: Optional[Settings] = None) -> bool:
    return dsn(pipeline, cfg) is not None


def pool(pipeline: str, cfg: Optional[Settings] = None) -> Engine:
    """El pool del pipeline. **Se crea aquí, en la primera consulta, no al arrancar.**

    Con 100 pipelines catalogados y 3 en uso se mantienen 3 pools; abrirlos todos al
    arranque rebasaría el `max_connections` del servidor mucho antes de llegar a 100.
    """
    cfg = cfg or settings()

    with _CANDADO:
        if pipeline not in _POOLS:
            destino = dsn(pipeline, cfg)
            if destino is None:
                raise PipelineUnavailable(f"el pipeline '{pipeline}' no tiene DSN en este despliegue")
            _POOLS[pipeline] = create_engine(
                destino,
                pool_size=cfg.pool_size,
                max_overflow=cfg.pool_max_overflow,
                pool_timeout=cfg.pool_timeout_s,
                # El servidor es un proceso de larga vida, a diferencia del CLI del ETL.
                pool_pre_ping=True,
                pool_recycle=3600,
                connect_args={"options": f"-c statement_timeout={cfg.statement_timeout_ms}"},
            )
        return _POOLS[pipeline]


def abierto(pipeline: str) -> bool:
    return pipeline in _POOLS


def estado(pipelines: Iterable[str], cfg: Optional[Settings] = None) -> dict[str, dict]:
    """Estado por pipeline para /ready. **No abre pools.**

    Distingue "sin DSN" de "pool sin abrir" porque la acción del operador es distinta
    en cada caso: la primera es configuración, la segunda es que nadie ha consultado.
    """
    cfg = cfg or settings()
    return {
        pipeline: {"dsn": disponible(pipeline, cfg), "pool": "abierto" if abierto(pipeline) else "sin abrir"}
        for pipeline in sorted(set(pipelines))
    }


def cerrar_todo() -> None:
    """Cierra los pools abiertos. Para el apagado del servidor y para las pruebas."""
    with _CANDADO:
        while _POOLS:
            _, motor = _POOLS.popitem()
            motor.dispose()
