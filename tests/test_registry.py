"""El registro de tokens: modelo, migraciones y conexión de escritura. Sin base de datos.

La pieza que hace posible probar el esquema sin PostgreSQL es el **modo offline** de
Alembic: genera el DDL sin conectarse, así que la revisión, `env.py` y el modelo se
ejercitan de verdad y el SQL resultante se puede afirmar línea por línea.

Lo que sí exige una base viva —la carrera de emisión concurrente, el borde de los noventa
días— vive en test_registry_db.py, marcado `integration`.
"""

import pytest
from alembic import command

from indicadores_sieej import connections, registry
from indicadores_sieej.errors import RegistryUnavailable

from .conftest import cfg as _cfg

DSN = "postgresql://registro:x@localhost:5432/registro"


def registry_cfg(**overrides):
    return _cfg(auth_mode="registro", registry_dsn=DSN, **overrides)


@pytest.fixture(autouse=True)
def _closed():
    """El motor es global: sin esto una prueba se lleva el de la anterior."""
    registry.close()
    yield
    registry.close()


@pytest.fixture
def ddl(capsys) -> str:
    """El DDL que Alembic aplicaría, generado sin tocar ninguna base."""
    command.upgrade(registry.alembic_config(registry_cfg()), "head", sql=True)
    return capsys.readouterr().out


# --- El esquema ---


def test_the_migration_creates_the_table(ddl):
    assert "CREATE TABLE tokens" in ddl
    assert "CREATE TABLE alembic_version" in ddl


def test_the_partial_unique_index_enforces_one_token_per_account(ddl):
    """Sin él, dos emisiones concurrentes para el mismo correo dejan dos tokens vivos:
    ordenar el UPDATE antes del INSERT no cierra la carrera."""
    assert "CREATE UNIQUE INDEX uq_tokens_correo_activo ON tokens (correo) WHERE revoked_at IS NULL" in ddl


def test_the_email_is_normalized_by_the_database(ddl):
    """Sin el CHECK, `A@b.mx` y `a@b.mx` son filas distintas y el índice de arriba deja
    de significar «un token por cuenta»."""
    assert "CHECK (correo = lower(btrim(correo)))" in ddl


def test_the_token_itself_is_never_stored(ddl):
    assert "token_hash VARCHAR(64) NOT NULL" in ddl
    assert "\n    token " not in ddl, "no puede existir una columna con el token en claro"


def test_every_column_is_commented(ddl):
    """La norma más fuerte de ETL-SIEEJ: los comentarios son la única documentación que
    tiene un operador frente a un psql sin este repositorio a la mano."""
    for column in registry.Token.__table__.columns:
        assert f"COMMENT ON COLUMN tokens.{column.name} IS" in ddl, f"falta el comentario de {column.name}"
    assert "COMMENT ON TABLE tokens IS" in ddl


def test_the_model_and_the_migration_do_not_drift(ddl):
    """El riesgo clásico de Alembic: el modelo cambia y la revisión se queda atrás.
    Los comentarios los emite la revisión, así que compararlos contra las columnas del
    modelo detecta que una sobra o falta en cualquiera de los dos lados."""
    commented = {line.split("tokens.")[1].split(" ")[0] for line in ddl.splitlines() if "COMMENT ON COLUMN" in line}
    assert commented == {column.name for column in registry.Token.__table__.columns}


def test_the_downgrade_undoes_the_upgrade(capsys):
    """Una revisión sin vuelta atrás es una revisión que nadie se atreve a aplicar."""
    command.downgrade(registry.alembic_config(registry_cfg()), "0001_tokens:base", sql=True)
    ddl = capsys.readouterr().out
    assert "DROP INDEX uq_tokens_correo_activo" in ddl
    assert "DROP TABLE tokens" in ddl


# --- La configuración ---


def test_alembic_ini_carries_no_dsn():
    """Ese archivo se versiona y un DSN lleva credenciales. La url la inyecta el código
    desde IIEGDB_REGISTRY_DSN, que es la misma que usa el servidor."""
    settings = [
        line for line in registry.ALEMBIC_INI.read_text(encoding="utf-8").splitlines() if not line.startswith("#")
    ]
    assert not any(line.strip().startswith("sqlalchemy.url") for line in settings)
    assert registry.alembic_config(registry_cfg()).get_main_option("sqlalchemy.url") == DSN


def test_without_a_dsn_the_registry_is_unavailable():
    with pytest.raises(RegistryUnavailable, match="no está configurado"):
        registry.dsn(_cfg())


def test_the_registry_dsn_has_no_fallback_to_the_read_only_role():
    """`IIEGDB_PG_*` es el rol de solo lectura de las 33 bases del ETL. Si el registro
    cayera en ese bloque cuando le falta el suyo, habría presión para concederle
    escritura — y eso rompería la garantía de solo lectura en todas a la vez."""
    with pytest.raises(RegistryUnavailable):
        registry.dsn(_cfg(pg_host="servidor-del-etl"))


# --- El motor ---


def test_the_engine_is_created_once_and_reused():
    cfg = registry_cfg()
    assert registry.engine(cfg) is registry.engine(cfg)


def test_the_registry_engine_never_lands_in_the_pipeline_pools():
    """`/ready` recorre esos pools y los mapea contra los pipelines del catálogo: el
    registro aparecería ahí como un pipeline que no existe."""
    registry.engine(registry_cfg())
    assert connections._POOLS == {}


def test_closing_the_registry_leaves_no_engine_behind():
    registry.engine(registry_cfg())
    registry.close()
    assert registry._ENGINE is None
