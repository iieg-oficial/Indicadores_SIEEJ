"""CLI de operación. No requiere base de datos.

Lo que se verifica sobre todo es la higiene de los flujos: el JSON no puede llevar
nada más que JSON, o deja de ser encadenable con jq.
"""

import json

import pytest

from indicadores_sieej import cli
from indicadores_sieej.catalog import load
from indicadores_sieej.errors import InvalidCatalog

from .conftest import ROW, cfg as _cfg


def test_listar_prints_clean_json(capsys):
    assert cli.main(["listar", "--tema", "empleo"]) == 0
    output = capsys.readouterr()
    assert len(json.loads(output.out)) == 5
    assert output.err == "", "ningún log puede ensuciar stdout ni aparecer aquí"


def test_describir_does_not_print_the_sql(capsys):
    assert cli.main(["describir", "pobreza_municipal"]) == 0
    metadata = json.loads(capsys.readouterr().out)
    assert "sql" not in metadata
    assert metadata["definicion"] and metadata["fuente"]


def test_ejecutar_returns_the_envelope(capsys, connection, monkeypatch):
    connection([ROW])
    monkeypatch.setattr(cli.engine, "settings", lambda: _cfg())
    assert cli.main(["ejecutar", "pobreza_municipal", "-p", "cve_geo=14039"]) == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["indicador"] == "pobreza_municipal"
    assert envelope["parametros_aplicados"] == {"cve_geo": "14039", "anio_min": None}


def test_ejecutar_with_an_undeclared_param_exits_with_error(capsys, connection, monkeypatch):
    connection([ROW])
    monkeypatch.setattr(cli.engine, "settings", lambda: _cfg())
    assert cli.main(["ejecutar", "pobreza_municipal", "-p", "municipio=14039"]) == 1
    output = capsys.readouterr()
    assert "parámetros desconocidos" in output.err
    assert output.out == "", "un error no imprime JSON a medias"


def test_describir_with_an_unknown_id_exits_with_error(capsys):
    assert cli.main(["describir", "no_existe"]) == 1
    assert "no existe en el catálogo" in capsys.readouterr().err


def test_validar_exits_with_zero_on_a_healthy_catalog(capsys):
    assert cli.main(["validar"]) == 0
    assert "12 indicadores válidos" in capsys.readouterr().err


def test_validar_exits_with_error_and_names_the_file(capsys, monkeypatch):
    def _blow_up():
        raise InvalidCatalog("catalogo/pobreza/roto.yaml: campo desconocido 'inventado'")

    monkeypatch.setattr(cli, "load", _blow_up)
    assert cli.main(["validar"]) == 1
    output = capsys.readouterr()
    assert "catalogo/pobreza/roto.yaml" in output.err
    assert output.out == ""


def test_validar_exits_with_error_on_an_empty_catalog(capsys, monkeypatch, tmp_path):
    """El gate de CI es lo que impide que un catálogo que no llegó pase por sano."""
    monkeypatch.setattr(cli, "load", lambda: load(tmp_path))
    assert cli.main(["validar"]) == 1
    output = capsys.readouterr()
    assert "ningún indicador" in output.err
    assert output.out == ""


def test_malformed_params_are_rejected():
    with pytest.raises(SystemExit, match="-p nombre=valor"):
        cli.main(["ejecutar", "pobreza_municipal", "-p", "cve_geo"])
