"""CLI de operación. No requiere base de datos.

Lo que se verifica sobre todo es la higiene de los flujos: el JSON no puede llevar
nada más que JSON, o deja de ser encadenable con jq.
"""

import json

import pytest

from indicadores_sieej import cli
from indicadores_sieej.errors import InvalidCatalog

from .conftest import FILA, cfg as _cfg


def test_listar_imprime_json_limpio(capsys):
    assert cli.main(["listar", "--tema", "empleo"]) == 0
    salida = capsys.readouterr()
    assert len(json.loads(salida.out)) == 5
    assert salida.err == "", "ningún log puede ensuciar stdout ni aparecer aquí"


def test_describir_no_imprime_el_sql(capsys):
    assert cli.main(["describir", "pobreza_municipal"]) == 0
    metadata = json.loads(capsys.readouterr().out)
    assert "sql" not in metadata
    assert metadata["definicion"] and metadata["fuente"]


def test_ejecutar_devuelve_el_sobre(capsys, conexion, monkeypatch):
    conexion([FILA])
    monkeypatch.setattr(cli.motor, "settings", lambda: _cfg())
    assert cli.main(["ejecutar", "pobreza_municipal", "-p", "cve_geo=14039"]) == 0
    sobre = json.loads(capsys.readouterr().out)
    assert sobre["indicador"] == "pobreza_municipal"
    assert sobre["parametros_aplicados"] == {"cve_geo": "14039", "anio_min": None}


def test_ejecutar_con_parametro_no_declarado_sale_con_error(capsys, conexion, monkeypatch):
    conexion([FILA])
    monkeypatch.setattr(cli.motor, "settings", lambda: _cfg())
    assert cli.main(["ejecutar", "pobreza_municipal", "-p", "municipio=14039"]) == 1
    salida = capsys.readouterr()
    assert "parámetros desconocidos" in salida.err
    assert salida.out == "", "un error no imprime JSON a medias"


def test_describir_un_id_inexistente_sale_con_error(capsys):
    assert cli.main(["describir", "no_existe"]) == 1
    assert "no existe en el catálogo" in capsys.readouterr().err


def test_validar_sale_con_cero_en_un_catalogo_sano(capsys):
    assert cli.main(["validar"]) == 0
    assert "12 indicadores válidos" in capsys.readouterr().err


def test_validar_sale_con_error_y_nombra_el_archivo(capsys, monkeypatch):
    def _revienta():
        raise InvalidCatalog("catalogo/pobreza/roto.yaml: campo desconocido 'inventado'")

    monkeypatch.setattr(cli, "cargar", _revienta)
    assert cli.main(["validar"]) == 1
    salida = capsys.readouterr()
    assert "catalogo/pobreza/roto.yaml" in salida.err
    assert salida.out == ""


def test_los_parametros_mal_escritos_se_rechazan():
    with pytest.raises(SystemExit, match="-p nombre=valor"):
        cli.main(["ejecutar", "pobreza_municipal", "-p", "cve_geo"])
