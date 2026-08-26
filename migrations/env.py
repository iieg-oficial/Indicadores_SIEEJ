"""Entorno de Alembic para el registro de API keys.

El DSN no se lee de `alembic.ini` sino de la configuración del servicio, que lo saca de
`IIEGDB_REGISTRY_DSN`. Una sola fuente de verdad, y ningún secreto versionado.

Se corre con `python -m indicadores_sieej.cli migrar`, que es lo que inyecta esa url.
"""

from alembic import context
from sqlalchemy import engine_from_config, pool

from indicadores_sieej.registry import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Genera el SQL sin conectarse. Sirve para revisar el DDL antes de aplicarlo."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
