"""Garantía 1 del contrato: el campo `sql` nunca sale del servidor.

CA-4 exige que se verifique con una prueba, no con revisión manual. El barrido toma
el `sql` real de cada indicador del catálogo, así que sigue siendo válido cuando el
catálogo crezca: no hay ninguna lista de indicadores escrita a mano.

El barrido cubre el motor y las dos superficies: lo que devuelven, lo que dicen sus
errores y lo que queda en los logs.
"""

import json
import logging

import pytest
import yaml
from fastmcp import Client
from fastmcp.exceptions import ToolError

from indicadores_sieej import connections, engine
from indicadores_sieej.catalog import CATALOG_DIR, find, get, load
from indicadores_sieej.errors import BankError, InvalidCatalog
from indicadores_sieej.mcp_server import mcp

from .conftest import ROW, cfg as _cfg

INDICATORS = list(load().values())

# Fragmentos que solo pueden venir del sql. El nombre de la vista queda fuera a
# propósito: viaja legítimamente en el campo `origen` de la metadata.
FRAGMENTS = sorted(
    {
        line.strip()
        for ind in INDICATORS
        for line in ind.sql.splitlines()
        if len(line.strip()) >= 25 and line.strip() != ind.origen
    }
)


def _without_sql(text: str, context: str) -> None:
    for ind in INDICATORS:
        assert ind.sql not in text, f"{context}: se filtró el sql de {ind.id}"
    for fragment in FRAGMENTS:
        assert fragment not in text, f"{context}: se filtró un fragmento de sql — {fragment!r}"


def test_there_are_fragments_to_sweep():
    # Si el catálogo cambiara de forma y esto quedara vacío, el resto pasaría en falso.
    assert len(FRAGMENTS) > 20


def test_find_carries_no_sql():
    _without_sql(json.dumps(find(), ensure_ascii=False, default=str), "find")


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_the_metadata_carries_no_sql(ind):
    _without_sql(json.dumps(ind.metadata(), ensure_ascii=False, default=str), f"metadata de {ind.id}")


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_the_response_envelope_carries_no_sql(ind, connection):
    connection([ROW])
    envelope = engine.execute(ind.id, cfg=_cfg())
    _without_sql(json.dumps(envelope, ensure_ascii=False, default=str), f"sobre de {ind.id}")


def test_the_sweep_detects_a_regression():
    """Canario: si alguien devolviera el modelo completo en vez de metadata(), esto
    tiene que fallar. Sin esta prueba, las de arriba podrían pasar en falso."""
    full = json.dumps(INDICATORS[0].model_dump(), ensure_ascii=False, default=str)
    with pytest.raises(AssertionError):
        _without_sql(full, "canario")


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_the_engine_errors_carry_no_sql(ind, connection, monkeypatch):
    messages = []

    connection([ROW] * 5001)
    for call in (
        lambda: engine.execute(ind.id, {"parametro_inventado": "x"}, cfg=_cfg()),
        lambda: engine.execute(ind.id, cfg=_cfg()),  # excede el límite
    ):
        with pytest.raises(BankError) as exc:
            call()
        messages.append(str(exc.value))

    connection(fails=True)
    with pytest.raises(BankError) as exc:
        engine.execute(ind.id, cfg=_cfg())
    messages.append(str(exc.value))

    monkeypatch.setattr(connections, "available", lambda *a, **k: False)
    with pytest.raises(BankError) as exc:
        engine.execute(ind.id, cfg=_cfg())
    messages.append(str(exc.value))

    _without_sql("\n".join(messages), f"errores de {ind.id}")


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_the_catalog_errors_carry_no_sql(ind, tmp_path):
    """La validación del sql es el lugar más fácil por donde se escaparía: tiene el
    sql en la mano cuando redacta el mensaje."""
    data = yaml.safe_load((CATALOG_DIR / ind.tema / f"{ind.id}.yaml").read_text(encoding="utf-8"))
    data["sql"] = ind.sql.replace("AS cve_geo", "AS clave")
    folder = tmp_path / ind.tema
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{ind.id}.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    with pytest.raises(InvalidCatalog) as exc:
        load(tmp_path)
    _without_sql(str(exc.value), f"catálogo inválido de {ind.id}")


def test_the_logs_carry_no_sql(connection, caplog):
    """Ni en INFO ni en ERROR: el registro de una consulta fallida es donde se cuela
    el sql si se registra la excepción de SQLAlchemy completa."""
    ind = INDICATORS[0]

    with caplog.at_level(logging.INFO):
        connection([ROW])
        engine.execute(ind.id, cfg=_cfg())

        connection(fails=True)
        with pytest.raises(BankError):
            engine.execute(ind.id, cfg=_cfg())

    _without_sql(caplog.text, "logs INFO+")


def test_get_exposes_the_sql_only_internally():
    # El motor sí necesita el sql: la garantía es que no salga, no que no exista.
    assert get(INDICATORS[0].id).sql


# --- La superficie MCP: lo que realmente ve el agente ---


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
async def test_the_mcp_responses_carry_no_sql(ind, connection, process_settings):
    """El barrido sobre el motor no basta: lo que ve el agente sale por aquí."""
    connection([ROW])
    async with Client(mcp) as client:
        responses = [
            await client.call_tool("listar_indicadores", {}),
            await client.call_tool("describir_indicador", {"id": ind.id}),
            await client.call_tool("consultar_indicador", {"id": ind.id}),
        ]
    for response in responses:
        _without_sql(json.dumps(response.data, ensure_ascii=False, default=str), f"tools MCP con {ind.id}")
        _without_sql("".join(block.text for block in response.content), f"contenido MCP con {ind.id}")


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
async def test_the_mcp_errors_carry_no_sql(ind, connection, process_settings):
    messages = []

    connection([ROW] * 5001)
    async with Client(mcp) as client:
        for tool, args in (
            ("describir_indicador", {"id": "no_existe"}),
            ("consultar_indicador", {"id": ind.id, "parametros": {"parametro_inventado": "x"}}),
            ("consultar_indicador", {"id": ind.id}),  # excede el límite
        ):
            with pytest.raises(ToolError) as exc:
                await client.call_tool(tool, args)
            messages.append(str(exc.value))

    _without_sql("\n".join(messages), f"errores MCP de {ind.id}")


# --- La superficie REST ---


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_the_rest_responses_carry_no_sql(ind, api, connection, process_settings):
    connection([ROW])
    for path in (
        "/v1/indicadores",
        f"/v1/indicadores/{ind.id}",
        f"/v1/indicadores/{ind.id}/datos",
    ):
        _without_sql(api.get(path).text, f"REST {path}")


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_the_rest_errors_carry_no_sql(ind, api, connection, process_settings):
    connection([ROW] * 5001)
    responses = [
        api.get("/v1/indicadores/no_existe"),
        api.get(f"/v1/indicadores/{ind.id}/datos", params={"parametro_inventado": "x"}),
        api.get(f"/v1/indicadores/{ind.id}/datos"),  # excede el límite
    ]
    connection(fails=True)
    responses.append(api.get(f"/v1/indicadores/{ind.id}/datos"))

    assert [r.status_code for r in responses] == [404, 400, 413, 502]
    _without_sql("\n".join(r.text for r in responses), f"errores REST de {ind.id}")


def test_the_openapi_carries_no_sql(api):
    """El esquema publicado describe las rutas, no el catálogo — pero es el lugar donde
    un `example` copiado a mano metería un sql sin que nadie lo note."""
    _without_sql(api.get("/openapi.json").text, "openapi")
