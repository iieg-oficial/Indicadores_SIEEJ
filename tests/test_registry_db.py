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


# --- El almacén contra la base ---


@pytest.fixture
def store(migrated) -> registry.PostgresApiKeyStore:
    return registry.PostgresApiKeyStore()


def _age(engine, correo: str, days: float) -> None:
    """Envejece el último uso de una key. Es lo que permite llegar al borde de los noventa
    días sin esperarlos, midiendo con el reloj de la base y no con el de Python."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE api_keys SET last_used_at = now() - make_interval(secs => :s) WHERE correo = :c"),
            {"s": days * 86400, "c": correo},
        )


def test_an_issued_key_verifies_and_carries_its_identity(store):
    key, stored = store.issue("alguien@iieg.mx")
    found = store.find(registry.hashed(key))

    assert found is not None
    assert found.id == stored.id
    assert found.scopes == ["indicadores:read"]
    assert found.prefijo == key[: registry.PREFIX_LEN]
    assert found.idle_s == 0


def test_the_key_in_the_clear_never_reaches_a_column(store, migrated):
    """La garantía completa exige mirar la fila entera, no solo la columna que se diseñó
    para el hash: una key en `prefijo` por un descuido sería igual de grave."""
    key, _ = store.issue("alguien@iieg.mx")
    with migrated.connect() as conn:
        fila = conn.execute(text("SELECT * FROM api_keys")).mappings().one()
    assert key not in str(dict(fila))
    assert fila["key_hash"] == registry.hashed(key)


def test_the_disuse_window_is_measured_with_the_database_clock(store, migrated):
    """El borde de los noventa días, contra `now()` de PostgreSQL. Con un solo reloj el
    desfase entre el servidor y el proceso ni siquiera es representable."""
    dentro, _ = store.issue("dentro@iieg.mx")
    fuera, _ = store.issue("fuera@iieg.mx")
    _age(migrated, "dentro@iieg.mx", 89.9)
    _age(migrated, "fuera@iieg.mx", 90.1)

    encontrada = store.find(registry.hashed(dentro))
    assert encontrada is not None
    assert 89 * 86400 < encontrada.idle_s < 90 * 86400
    assert store.find(registry.hashed(fuera)) is None


def test_the_refresh_is_throttled_by_the_database(store, migrated):
    """El `WHERE` del UPDATE es lo que acota, no el llamador: dos workers que refresquen
    a la vez no se estorban, y el que llega tarde actualiza cero filas."""
    key, stored = store.issue("alguien@iieg.mx")
    _age(migrated, "alguien@iieg.mx", 2 / 24)  # dos horas parada

    store.touch(stored.id, throttle_s=3600)
    assert store.find(registry.hashed(key)).idle_s == 0

    _age(migrated, "alguien@iieg.mx", 0.5 / 24)  # media hora, por debajo del acotado
    store.touch(stored.id, throttle_s=3600)
    assert store.find(registry.hashed(key)).idle_s > 1000


def test_reissuing_rotates_the_key_and_kills_the_old_one(store, migrated):
    """La reemisión es la rotación, y también la vía de recuperación de quien perdió la
    suya. Que la anterior siga viva convertiría cada recuperación en una key de más."""
    vieja, _ = store.issue("alguien@iieg.mx")
    nueva, _ = store.issue("alguien@iieg.mx")

    assert store.find(registry.hashed(vieja)) is None
    assert store.find(registry.hashed(nueva)) is not None
    with migrated.connect() as conn:
        activas = conn.execute(text("SELECT count(*) FROM api_keys WHERE revoked_at IS NULL")).scalar()
    assert activas == 1


def test_revoking_leaves_the_key_unusable(store):
    key, stored = store.issue("alguien@iieg.mx")
    store.revoke(stored.id)
    assert store.find(registry.hashed(key)) is None


def test_two_concurrent_issues_for_one_account_leave_exactly_one_active(store, migrated):
    """La carrera de verdad, con dos conexiones peleando por el índice parcial. El
    perdedor reintenta una vez y el resultado sigue siendo una sola key activa — que es
    lo que ninguna prueba con un doble puede demostrar."""
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        keys = [f.result()[0] for f in [pool.submit(store.issue, "alguien@iieg.mx") for _ in range(2)]]

    with migrated.connect() as conn:
        activas = conn.execute(text("SELECT count(*) FROM api_keys WHERE revoked_at IS NULL")).scalar()
    assert activas == 1
    assert sum(store.find(registry.hashed(k)) is not None for k in keys) == 1
