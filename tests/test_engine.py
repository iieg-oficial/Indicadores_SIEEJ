"""Motor de ejecución, con el doble de conexión de conftest. No requiere base de datos."""

import logging

import pytest

from indicadores_sieej import connections, engine
from indicadores_sieej.catalog import COLUMNS, get
from indicadores_sieej.errors import (
    InvalidParameters,
    PipelineUnavailable,
    QueryError,
    RowLimitExceeded,
)

from .conftest import ROW, cfg as _cfg


# --- Parámetros y coacción de tipos ---


def test_coerces_to_the_declared_type(connection):
    fake = connection()
    engine.execute("incidencia_delictiva_municipal", cfg=_cfg(), anio_min="2020")
    assert fake.binds["anio_min"] == 2020


def test_value_that_cannot_be_coerced(connection):
    connection()
    with pytest.raises(InvalidParameters, match="no es un int válido"):
        engine.execute("incidencia_delictiva_municipal", cfg=_cfg(), anio_min="dos mil")


def test_undeclared_param(connection):
    connection()
    with pytest.raises(InvalidParameters) as exc:
        engine.execute("incidencia_delictiva_municipal", cfg=_cfg(), municipio="14039")
    assert str(exc.value) == "incidencia_delictiva_municipal: parámetros desconocidos ['municipio']"


def test_missing_required_param(connection, monkeypatch):
    # Ninguno del piloto es requerido: se fuerza uno sobre un indicador real.
    ind = get("incidencia_delictiva_municipal")
    required = ind.model_copy(deep=True)
    required.parametros[0].requerido = True
    monkeypatch.setattr(engine, "get", lambda _: required)
    connection()
    with pytest.raises(InvalidParameters, match="falta el parámetro requerido 'cve_geo'"):
        engine.execute("incidencia_delictiva_municipal", cfg=_cfg())


def test_absent_optional_travels_as_null(connection):
    fake = connection()
    engine.execute("incidencia_delictiva_municipal", cfg=_cfg())
    assert fake.binds == {"cve_geo": None, "tipo_delito": None, "anio_min": None}


# --- Binds, envoltura y solo lectura ---


def test_values_never_reach_the_sql_text(connection):
    """Si alguien reintroduce concatenación, el valor aparece en el sql y esto falla."""
    fake = connection()
    engine.execute("incidencia_delictiva_municipal", cfg=_cfg(), cve_geo="14039")
    assert "14039" not in str(fake.query)
    assert fake.binds["cve_geo"] == "14039"


def test_the_query_is_wrapped_and_bounded(connection):
    fake = connection()
    engine.execute("incidencia_delictiva_municipal", cfg=_cfg(row_limit=10))
    query = str(fake.query)
    assert query.startswith("SELECT * FROM (")
    assert query.endswith(") _bank LIMIT 11")


def test_the_transaction_is_read_only(connection):
    fake = connection()
    engine.execute("incidencia_delictiva_municipal", cfg=_cfg())
    assert fake.options == {"postgresql_readonly": True}


# --- Límite ---


def test_the_limit_fails_loudly(connection):
    connection([ROW] * 5001)
    with pytest.raises(RowLimitExceeded) as exc:
        engine.execute("incidencia_delictiva_municipal", cfg=_cfg())
    assert str(exc.value) == (
        "incidencia_delictiva_municipal: la consulta excede 5000 filas; "
        "acota con ['anio_min', 'cve_geo', 'tipo_delito']"
    )


def test_the_exact_limit_does_not_fail(connection):
    connection([ROW] * 5000)
    assert len(engine.execute("incidencia_delictiva_municipal", cfg=_cfg())["filas"]) == 5000


# --- Sobre de respuesta ---


def test_the_envelope_carries_metadata_params_and_notes(connection):
    connection([ROW])
    envelope = engine.execute("incidencia_delictiva_municipal", cfg=_cfg(), cve_geo="14039")
    assert envelope["indicador"] == "incidencia_delictiva_municipal"
    assert envelope["unidad"] and envelope["fuente"] and envelope["nombre"]
    assert envelope["notas"], "notas viaja siempre que el indicador la tenga"
    assert envelope["parametros_aplicados"] == {"cve_geo": "14039", "tipo_delito": None, "anio_min": None}
    assert list(envelope["filas"][0]) == list(COLUMNS)


# --- Fallas de infraestructura ---


def test_pipeline_without_dsn(monkeypatch):
    monkeypatch.setattr(connections, "available", lambda *a, **k: False)
    with pytest.raises(PipelineUnavailable) as exc:
        engine.execute("incidencia_delictiva_municipal", cfg=_cfg())
    assert str(exc.value) == "incidencia_delictiva_municipal: indicador no disponible en este despliegue"


def test_a_dead_database_leaks_nothing(connection, caplog):
    connection(fails=True)
    with caplog.at_level(logging.INFO):
        with pytest.raises(QueryError, match="error al consultar la base"):
            engine.execute("incidencia_delictiva_municipal", cfg=_cfg())
    assert "referencia:" in caplog.text or "consulta fallida" in caplog.text
