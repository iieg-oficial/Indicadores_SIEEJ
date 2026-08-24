"""Motor de ejecución, con el doble de conexión de conftest. No requiere base de datos."""

import logging

import pytest

from indicadores_sieej import conexiones, motor
from indicadores_sieej.catalogo import COLUMNAS, obtener
from indicadores_sieej.errores import (
    ErrorDeConsulta,
    LimiteExcedido,
    ParametrosInvalidos,
    PipelineNoDisponible,
)

from .conftest import FILA, cfg as _cfg


# --- Parámetros y coacción de tipos ---


def test_coacciona_al_tipo_declarado(conexion):
    falsa = conexion()
    motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg(), anio_min="2020")
    assert falsa.binds["anio_min"] == 2020


def test_valor_no_coaccionable(conexion):
    conexion()
    with pytest.raises(ParametrosInvalidos, match="no es un int válido"):
        motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg(), anio_min="dos mil")


def test_parametro_no_declarado(conexion):
    conexion()
    with pytest.raises(ParametrosInvalidos) as exc:
        motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg(), municipio="14039")
    assert str(exc.value) == "incidencia_delictiva_municipal: parámetros desconocidos ['municipio']"


def test_parametro_requerido_ausente(conexion, monkeypatch):
    # Ninguno del piloto es requerido: se fuerza uno sobre un indicador real.
    ind = obtener("incidencia_delictiva_municipal")
    requerido = ind.model_copy(deep=True)
    requerido.parametros[0].requerido = True
    monkeypatch.setattr(motor, "obtener", lambda _: requerido)
    conexion()
    with pytest.raises(ParametrosInvalidos, match="falta el parámetro requerido 'cve_geo'"):
        motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())


def test_opcional_ausente_viaja_como_null(conexion):
    falsa = conexion()
    motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())
    assert falsa.binds == {"cve_geo": None, "tipo_delito": None, "anio_min": None}


# --- Binds, envoltura y solo lectura ---


def test_los_valores_no_entran_al_texto_del_sql(conexion):
    """Si alguien reintroduce concatenación, el valor aparece en el sql y esto falla."""
    falsa = conexion()
    motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg(), cve_geo="14039")
    assert "14039" not in str(falsa.consulta)
    assert falsa.binds["cve_geo"] == "14039"


def test_la_consulta_va_envuelta_y_acotada(conexion):
    falsa = conexion()
    motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg(limite_filas=10))
    consulta = str(falsa.consulta)
    assert consulta.startswith("SELECT * FROM (")
    assert consulta.endswith(") _banco LIMIT 11")


def test_la_transaccion_es_de_solo_lectura(conexion):
    falsa = conexion()
    motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())
    assert falsa.opciones == {"postgresql_readonly": True}


# --- Límite ---


def test_el_limite_falla_ruidoso(conexion):
    conexion([FILA] * 5001)
    with pytest.raises(LimiteExcedido) as exc:
        motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())
    assert str(exc.value) == (
        "incidencia_delictiva_municipal: la consulta excede 5000 filas; "
        "acota con ['anio_min', 'cve_geo', 'tipo_delito']"
    )


def test_el_limite_justo_no_falla(conexion):
    conexion([FILA] * 5000)
    assert len(motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())["filas"]) == 5000


# --- Sobre de respuesta ---


def test_el_sobre_lleva_metadata_parametros_y_notas(conexion):
    conexion([FILA])
    sobre = motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg(), cve_geo="14039")
    assert sobre["indicador"] == "incidencia_delictiva_municipal"
    assert sobre["unidad"] and sobre["fuente"] and sobre["nombre"]
    assert sobre["notas"], "notas viaja siempre que el indicador la tenga"
    assert sobre["parametros_aplicados"] == {"cve_geo": "14039", "tipo_delito": None, "anio_min": None}
    assert list(sobre["filas"][0]) == list(COLUMNAS)


# --- Fallas de infraestructura ---


def test_pipeline_sin_dsn(monkeypatch):
    monkeypatch.setattr(conexiones, "disponible", lambda *a, **k: False)
    with pytest.raises(PipelineNoDisponible) as exc:
        motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())
    assert str(exc.value) == "incidencia_delictiva_municipal: indicador no disponible en este despliegue"


def test_base_caida_no_filtra_nada(conexion, caplog):
    conexion(falla=True)
    with caplog.at_level(logging.INFO):
        with pytest.raises(ErrorDeConsulta, match="error al consultar la base"):
            motor.ejecutar("incidencia_delictiva_municipal", cfg=_cfg())
    assert "referencia:" in caplog.text or "consulta fallida" in caplog.text
