"""Resolución del DSN y ciclo de vida de los pools. No abre ninguna conexión.

`create_engine` no conecta: arma el pool y espera. Por eso estas pruebas pueden
verificar el dimensionamiento sin una base viva.
"""

import pytest

from indicadores_sieej import connections
from indicadores_sieej.errors import PipelineUnavailable

from .conftest import cfg as _cfg


class _FakeEngine:
    def dispose(self):
        pass


@pytest.fixture(autouse=True)
def no_pools():
    connections.close_all()
    yield
    connections.close_all()


def test_an_explicit_dsn_wins_over_the_default_server(monkeypatch):
    monkeypatch.setenv("IIEGDB_DSN_CONAPO", "postgresql://u:p@otro:5432/conapo_2024")
    assert connections.dsn("conapo", _cfg()) == "postgresql://u:p@otro:5432/conapo_2024"


def test_the_default_server_builds_the_dsn_from_the_pipeline_name(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    url = connections.dsn("ilmm", _cfg(pipelines="ilmm"))
    assert url.database == "ilmm"
    assert (url.host, url.port, url.username) == ("h", 5432, "u")
    assert url.query["sslmode"] == "require"


def test_the_password_needs_no_url_encoding(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    url = connections.dsn("ilmm", _cfg(pipelines="ilmm", pg_password="p@ss:word/raro"))
    assert "p%40ss%3Aword%2Fraro" in url.render_as_string(hide_password=False)


def test_a_pipeline_outside_the_list_has_no_dsn(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    cfg = _cfg(pipelines="enoe_microdatos")
    assert connections.dsn("ilmm", cfg) is None
    assert not connections.available("ilmm", cfg)
    with pytest.raises(PipelineUnavailable):
        connections.pool("ilmm", cfg)


def test_the_pool_is_born_on_the_first_query_and_is_reused(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    cfg = _cfg(pipelines="ilmm")
    assert not connections.is_open("ilmm"), "no debe haber pools antes de la primera consulta"

    first = connections.pool("ilmm", cfg)
    assert connections.is_open("ilmm")
    assert connections.pool("ilmm", cfg) is first, "un solo pool por pipeline"


def test_the_pool_is_sized_as_the_configuration_says(monkeypatch):
    # Se capturan los argumentos en vez de leer los atributos privados del pool de
    # SQLAlchemy, que no son parte de su API pública.
    kwargs = {}
    monkeypatch.setattr(connections, "create_engine", lambda dsn, **kw: kwargs.update(kw) or _FakeEngine())
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)

    connections.pool("ilmm", _cfg(pipelines="ilmm", pool_size=4, pool_max_overflow=6))
    assert kwargs["pool_size"] == 4
    assert kwargs["max_overflow"] == 6
    assert kwargs["pool_timeout"] == 10
    # Proceso de larga vida, a diferencia del CLI del ETL.
    assert kwargs["pool_pre_ping"] is True
    assert kwargs["pool_recycle"] == 3600
    assert kwargs["connect_args"] == {"options": "-c statement_timeout=15000"}


def test_status_reports_without_opening_pools(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    monkeypatch.delenv("IIEGDB_DSN_CONAPO", raising=False)
    cfg = _cfg(pipelines="ilmm")

    status = connections.status(["ilmm", "conapo"], cfg)
    assert status == {
        "conapo": {"dsn": False, "pool": "unopened"},
        "ilmm": {"dsn": True, "pool": "unopened"},
    }
    assert not connections.is_open("ilmm"), "/ready no debe abrir pools"

    connections.pool("ilmm", cfg)
    assert connections.status(["ilmm"], cfg)["ilmm"]["pool"] == "open"
