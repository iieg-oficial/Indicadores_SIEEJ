"""Las tres tools MCP, con un cliente en memoria. Sin puerto y sin base de datos.

El cliente de FastMCP habla el protocolo completo contra el servidor en proceso, así
que lo que se prueba aquí es lo que verá un agente: los nombres de las tools, sus
anotaciones, la forma de la salida y el texto de cada error.
"""

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from indicadores_sieej import engine
from indicadores_sieej.catalog import SUMMARY_FIELDS, get
from indicadores_sieej.mcp_server import mcp

from .conftest import ROW

TOOLS = ("listar_indicadores", "describir_indicador", "consultar_indicador")

# Un indicador real del piloto: sus tres parámetros son todos opcionales.
INDICATOR = "incidencia_delictiva_municipal"


@pytest.fixture
def client():
    return Client(mcp)


# --- Contrato de las tools ---


async def test_the_three_tools_are_registered(client):
    async with client:
        assert sorted(tool.name for tool in await client.list_tools()) == sorted(TOOLS)


async def test_the_three_tools_are_read_only_and_closed_world(client):
    """Se verifican, no se asumen: son lo que le dice al agente que puede llamarlas."""
    async with client:
        for tool in await client.list_tools():
            assert tool.annotations.readOnlyHint is True, tool.name
            assert tool.annotations.openWorldHint is False, tool.name


async def test_every_tool_describes_itself(client):
    """Sin descripción el agente no sabe cuál llamar, y el descubrimiento se rompe."""
    async with client:
        for tool in await client.list_tools():
            assert tool.description, tool.name


# --- listar_indicadores ---


async def test_list_returns_the_reduced_view(client):
    async with client:
        result = await client.call_tool("listar_indicadores", {})
    assert result.data
    for row in result.data:
        assert tuple(row) == SUMMARY_FIELDS


async def test_list_filters_by_tema_and_by_nivel(client):
    async with client:
        by_tema = (await client.call_tool("listar_indicadores", {"tema": "empleo"})).data
        by_nivel = (await client.call_tool("listar_indicadores", {"nivel": "estatal"})).data
    assert by_tema and {row["tema"] for row in by_tema} == {"empleo"}
    assert by_nivel and {row["nivel"] for row in by_nivel} == {"estatal"}


async def test_list_without_matches_returns_an_empty_list(client):
    """Vacío no es un error: el agente está explorando, no fallando."""
    async with client:
        result = await client.call_tool("listar_indicadores", {"tema": "no_existe"})
    assert result.data == []


# --- describir_indicador ---


async def test_describe_returns_the_full_metadata_with_its_parameters(client):
    async with client:
        result = await client.call_tool("describir_indicador", {"id": INDICATOR})
    assert result.data["id"] == INDICATOR
    assert result.data["definicion"] and result.data["fuente"]
    # `descripcion` de cada parámetro es lo que el agente lee para saber qué mandar.
    assert all(param["descripcion"] for param in result.data["parametros"])
    assert "sql" not in result.data


async def test_describe_with_an_unknown_id_carries_the_documented_text(client):
    async with client:
        with pytest.raises(ToolError) as exc:
            await client.call_tool("describir_indicador", {"id": "no_existe"})
    assert "Indicador 'no_existe' no existe en el catálogo" in str(exc.value)


# --- consultar_indicador ---


async def test_query_returns_the_envelope(client, connection, process_settings):
    connection([ROW])
    async with client:
        result = await client.call_tool("consultar_indicador", {"id": INDICATOR})
    envelope = result.data
    assert envelope["indicador"] == INDICATOR
    assert envelope["unidad"] and envelope["fuente"]
    assert envelope["parametros_aplicados"] == {"cve_geo": None, "tipo_delito": None, "anio_min": None}
    assert len(envelope["filas"]) == 1


async def test_query_passes_the_parameters_to_the_engine(client, connection, process_settings):
    fake = connection([ROW])
    async with client:
        await client.call_tool("consultar_indicador", {"id": INDICATOR, "parametros": {"anio_min": 2020}})
    assert fake.binds["anio_min"] == 2020


async def test_query_with_an_unknown_parameter(client, connection, process_settings):
    connection()
    async with client:
        with pytest.raises(ToolError) as exc:
            await client.call_tool("consultar_indicador", {"id": INDICATOR, "parametros": {"municipio": "14039"}})
    assert f"{INDICATOR}: parámetros desconocidos ['municipio']" in str(exc.value)


async def test_query_with_a_missing_required_parameter(client, connection, process_settings, monkeypatch):
    # Ninguno del piloto es requerido: se fuerza uno sobre un indicador real.
    required = get(INDICATOR).model_copy(deep=True)
    required.parametros[0].requerido = True
    monkeypatch.setattr(engine, "get", lambda _: required)
    connection()
    async with client:
        with pytest.raises(ToolError) as exc:
            await client.call_tool("consultar_indicador", {"id": INDICATOR})
    assert f"{INDICATOR}: falta el parámetro requerido 'cve_geo'" in str(exc.value)


async def test_query_exceeding_the_limit_names_the_parameters_to_narrow_with(client, connection, process_settings):
    """El error llega íntegro: esa lista es con lo que el agente reintenta."""
    connection([ROW] * 5001)
    async with client:
        with pytest.raises(ToolError) as exc:
            await client.call_tool("consultar_indicador", {"id": INDICATOR})
    assert f"{INDICATOR}: la consulta excede 5000 filas; acota con ['anio_min', 'cve_geo', 'tipo_delito']" in str(
        exc.value
    )


async def test_query_of_an_unavailable_pipeline(client, connection, process_settings, monkeypatch):
    connection()
    monkeypatch.setattr("indicadores_sieej.connections.available", lambda *a, **k: False)
    async with client:
        with pytest.raises(ToolError) as exc:
            await client.call_tool("consultar_indicador", {"id": INDICATOR})
    assert f"{INDICATOR}: indicador no disponible en este despliegue" in str(exc.value)
