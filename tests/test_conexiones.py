"""Resolución del DSN y ciclo de vida de los pools. No abre ninguna conexión.

`create_engine` no conecta: arma el pool y espera. Por eso estas pruebas pueden
verificar el dimensionamiento sin una base viva.
"""

import pytest

from indicadores_sieej import connections
from indicadores_sieej.errors import PipelineUnavailable

from .conftest import cfg as _cfg


class _MotorFalso:
    def dispose(self):
        pass


@pytest.fixture(autouse=True)
def sin_pools():
    connections.close_all()
    yield
    connections.close_all()


def test_el_dsn_propio_gana_sobre_el_servidor_por_defecto(monkeypatch):
    monkeypatch.setenv("IIEGDB_DSN_CONAPO", "postgresql://u:p@otro:5432/conapo_2024")
    assert connections.dsn("conapo", _cfg()) == "postgresql://u:p@otro:5432/conapo_2024"


def test_el_servidor_por_defecto_arma_el_dsn_con_el_nombre_del_pipeline(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    url = connections.dsn("ilmm", _cfg(pipelines="ilmm"))
    assert url.database == "ilmm"
    assert (url.host, url.port, url.username) == ("h", 5432, "u")
    assert url.query["sslmode"] == "require"


def test_la_contrasena_no_necesita_ir_url_encodeada(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    url = connections.dsn("ilmm", _cfg(pipelines="ilmm", pg_password="p@ss:word/raro"))
    assert "p%40ss%3Aword%2Fraro" in url.render_as_string(hide_password=False)


def test_un_pipeline_fuera_de_la_lista_no_tiene_dsn(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    settings = _cfg(pipelines="enoe_microdatos")
    assert connections.dsn("ilmm", settings) is None
    assert not connections.available("ilmm", settings)
    with pytest.raises(PipelineUnavailable):
        connections.pool("ilmm", settings)


def test_el_pool_nace_en_la_primera_consulta_y_se_reutiliza(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    settings = _cfg(pipelines="ilmm")
    assert not connections.is_open("ilmm"), "no debe haber pools antes de la primera consulta"

    primero = connections.pool("ilmm", settings)
    assert connections.is_open("ilmm")
    assert connections.pool("ilmm", settings) is primero, "un solo pool por pipeline"


def test_el_pool_se_dimensiona_como_dice_la_configuracion(monkeypatch):
    # Se capturan los argumentos en vez de leer los atributos privados del pool de
    # SQLAlchemy, que no son parte de su API pública.
    argumentos = {}
    monkeypatch.setattr(connections, "create_engine", lambda dsn, **kw: argumentos.update(kw) or _MotorFalso())
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)

    connections.pool("ilmm", _cfg(pipelines="ilmm", pool_size=4, pool_max_overflow=6))
    assert argumentos["pool_size"] == 4
    assert argumentos["max_overflow"] == 6
    assert argumentos["pool_timeout"] == 10
    # Proceso de larga vida, a diferencia del CLI del ETL.
    assert argumentos["pool_pre_ping"] is True
    assert argumentos["pool_recycle"] == 3600
    assert argumentos["connect_args"] == {"options": "-c statement_timeout=15000"}


def test_estado_reporta_sin_abrir_pools(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    monkeypatch.delenv("IIEGDB_DSN_CONAPO", raising=False)
    settings = _cfg(pipelines="ilmm")

    estado = connections.status(["ilmm", "conapo"], settings)
    assert estado == {
        "conapo": {"dsn": False, "pool": "unopened"},
        "ilmm": {"dsn": True, "pool": "unopened"},
    }
    assert not connections.is_open("ilmm"), "/ready no debe abrir pools"

    connections.pool("ilmm", settings)
    assert connections.status(["ilmm"], settings)["ilmm"]["pool"] == "open"
