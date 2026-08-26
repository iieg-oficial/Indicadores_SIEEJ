"""El registro de API keys contra un PostgreSQL de verdad. **No corre en CI.**

Lo que está aquí es lo que un doble no puede demostrar: que la migración se aplica de
verdad, que volver a aplicarla no rompe nada, y que el índice único parcial cierra la
carrera de emisión concurrente.

Se corre a mano con una base vacía:

    IIEGDB_REGISTRY_DSN=postgresql://...  pytest -m integration
"""

import os

import pytest
from sqlalchemy import inspect, text

from indicadores_sieej import registry

pytestmark = pytest.mark.integration


@pytest.fixture
def migrated():
    # Se salta en vez de reventar: un `pytest` pelado en la máquina de alguien no tiene
    # por qué fallar por no tener una base a mano.
    if not os.environ.get("IIEGDB_REGISTRY_DSN"):
        pytest.skip("requiere IIEGDB_REGISTRY_DSN apuntando a una base vacía")
    registry.close()
    registry.migrate()
    yield registry.engine()
    with registry.engine().begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS api_keys"))
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    registry.close()


def test_migrating_twice_is_harmless(migrated):
    """Alembic lleva su propia tabla de versiones: la segunda corrida no hace nada."""
    registry.migrate()
    assert "api_keys" in inspect(migrated).get_table_names()


def test_the_comments_reach_the_database(migrated):
    """Es la única documentación del esquema para quien llega con un psql y nada más."""
    with migrated.connect() as conn:
        table = conn.execute(text("SELECT obj_description('api_keys'::regclass)")).scalar()
        columns = conn.execute(
            text("""
                SELECT a.attname, col_description(a.attrelid, a.attnum)
                  FROM pg_attribute a
                 WHERE a.attrelid = 'api_keys'::regclass AND a.attnum > 0 AND NOT a.attisdropped
            """)
        ).all()
    assert table
    assert all(comment for _, comment in columns), [name for name, comment in columns if not comment]


def test_the_email_check_rejects_a_denormalized_address(migrated):
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with migrated.begin() as conn:
            conn.execute(
                text("INSERT INTO api_keys (correo, key_hash, prefijo) VALUES (:c, :h, :p)"),
                {"c": "Mayusculas@iieg.mx", "h": "a" * 64, "p": "iieg_a"},
            )


def test_two_active_keys_for_one_account_are_impossible(migrated):
    """El corazón de la decisión: una API key activa por correo, garantizada por la base y
    no por la aplicación. Sin el índice parcial, esto pasaría sin protestar."""
    from sqlalchemy.exc import IntegrityError

    with migrated.begin() as conn:
        conn.execute(
            text("INSERT INTO api_keys (correo, key_hash, prefijo) VALUES (:c, :h, :p)"),
            {"c": "alguien@iieg.mx", "h": "a" * 64, "p": "iieg_a"},
        )

    with pytest.raises(IntegrityError):
        with migrated.begin() as conn:
            conn.execute(
                text("INSERT INTO api_keys (correo, key_hash, prefijo) VALUES (:c, :h, :p)"),
                {"c": "alguien@iieg.mx", "h": "b" * 64, "p": "iieg_b"},
            )


def test_a_revoked_key_frees_the_account(migrated):
    """El índice es parcial justamente para esto: reemitir tiene que poder."""
    with migrated.begin() as conn:
        conn.execute(
            text("INSERT INTO api_keys (correo, key_hash, prefijo) VALUES (:c, :h, :p)"),
            {"c": "alguien@iieg.mx", "h": "a" * 64, "p": "iieg_a"},
        )
        conn.execute(text("UPDATE api_keys SET revoked_at = now() WHERE correo = 'alguien@iieg.mx'"))
        conn.execute(
            text("INSERT INTO api_keys (correo, key_hash, prefijo) VALUES (:c, :h, :p)"),
            {"c": "alguien@iieg.mx", "h": "b" * 64, "p": "iieg_b"},
        )
        activos = conn.execute(
            text("SELECT count(*) FROM api_keys WHERE correo = 'alguien@iieg.mx' AND revoked_at IS NULL")
        ).scalar()
    assert activos == 1
