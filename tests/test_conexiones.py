"""Resolución del DSN y ciclo de vida de los pools. No abre ninguna conexión.

`create_engine` no conecta: arma el pool y espera. Por eso estas pruebas pueden
verificar el dimensionamiento sin una base viva.
"""

import pytest

from indicadores_sieej import conexiones
from indicadores_sieej.errores import PipelineNoDisponible

from .conftest import cfg as _cfg


class _MotorFalso:
    def dispose(self):
        pass


@pytest.fixture(autouse=True)
def sin_pools():
    conexiones.cerrar_todo()
    yield
    conexiones.cerrar_todo()


def test_el_dsn_propio_gana_sobre_el_servidor_por_defecto(monkeypatch):
    monkeypatch.setenv("IIEGDB_DSN_CONAPO", "postgresql://u:p@otro:5432/conapo_2024")
    assert conexiones.dsn("conapo", _cfg()) == "postgresql://u:p@otro:5432/conapo_2024"


def test_el_servidor_por_defecto_arma_el_dsn_con_el_nombre_del_pipeline(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    url = conexiones.dsn("ilmm", _cfg(pipelines="ilmm"))
    assert url.database == "ilmm"
    assert (url.host, url.port, url.username) == ("h", 5432, "u")
    assert url.query["sslmode"] == "require"


def test_la_contrasena_no_necesita_ir_url_encodeada(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    url = conexiones.dsn("ilmm", _cfg(pipelines="ilmm", pg_password="p@ss:word/raro"))
    assert "p%40ss%3Aword%2Fraro" in url.render_as_string(hide_password=False)


def test_un_pipeline_fuera_de_la_lista_no_tiene_dsn(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    settings = _cfg(pipelines="enoe_microdatos")
    assert conexiones.dsn("ilmm", settings) is None
    assert not conexiones.disponible("ilmm", settings)
    with pytest.raises(PipelineNoDisponible):
        conexiones.pool("ilmm", settings)


def test_el_pool_nace_en_la_primera_consulta_y_se_reutiliza(monkeypatch):
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)
    settings = _cfg(pipelines="ilmm")
    assert not conexiones.abierto("ilmm"), "no debe haber pools antes de la primera consulta"

    primero = conexiones.pool("ilmm", settings)
    assert conexiones.abierto("ilmm")
    assert conexiones.pool("ilmm", settings) is primero, "un solo pool por pipeline"


def test_el_pool_se_dimensiona_como_dice_la_configuracion(monkeypatch):
    # Se capturan los argumentos en vez de leer los atributos privados del pool de
    # SQLAlchemy, que no son parte de su API pública.
    argumentos = {}
    monkeypatch.setattr(conexiones, "create_engine", lambda dsn, **kw: argumentos.update(kw) or _MotorFalso())
    monkeypatch.delenv("IIEGDB_DSN_ILMM", raising=False)

    conexiones.pool("ilmm", _cfg(pipelines="ilmm", pool_size=4, pool_max_overflow=6))
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

    estado = conexiones.estado(["ilmm", "conapo"], settings)
    assert estado == {
        "conapo": {"dsn": False, "pool": "sin abrir"},
        "ilmm": {"dsn": True, "pool": "sin abrir"},
    }
    assert not conexiones.abierto("ilmm"), "/ready no debe abrir pools"

    conexiones.pool("ilmm", settings)
    assert conexiones.estado(["ilmm"], settings)["ilmm"]["pool"] == "abierto"
