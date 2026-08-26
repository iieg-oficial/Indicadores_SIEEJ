"""Las tres tools MCP del banco, servidas en `/mcp`.

Cada tool delega **1:1** en el motor: aquí no se toma ninguna decisión de negocio, solo
se traduce transporte. Si alguna vez hace falta lógica en este archivo, la capa
equivocada es esta.

Las tres se anotan `readOnlyHint=True` y `openWorldHint=False`: el banco solo lee, y
solo lee del catálogo curado.

Los nombres de las tools, sus parámetros y sus descripciones van en español porque son
la superficie que consume el agente — el contrato de docs/superficies.md — no
vocabulario interno.
"""

from contextlib import contextmanager
from typing import Optional

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from indicadores_sieej import engine
from indicadores_sieej.catalog import find, get
from indicadores_sieej.errors import BankError

# Solo lectura y mundo cerrado: no hay efectos, y todo sale del catálogo del IIEG.
READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)

mcp = FastMCP(
    name="Banco de indicadores IIEG",
    instructions=(
        "Catálogo curado de indicadores del IIEG. Empieza siempre por "
        "`listar_indicadores` para descubrir qué hay, sigue con `describir_indicador` "
        "para saber qué parámetros acepta uno, y consulta los datos con "
        "`consultar_indicador`. No existe forma de escribir SQL: solo se eligen "
        "indicadores y se les pasan valores a sus parámetros declarados."
    ),
)


@contextmanager
def _surfaced():
    """Traduce los errores del motor a errores de tool, **sin reescribir el texto**.

    La lista de parámetros que trae el mensaje es justamente lo que permite al agente
    reintentar bien; resumirlo lo dejaría sin con qué corregirse. Se convierte a
    `ToolError` para que el mensaje viaje íntegro sin depender de `mask_error_details`.
    """
    try:
        yield
    except BankError as exc:
        raise ToolError(str(exc)) from None


@mcp.tool(name="listar_indicadores", annotations=READ_ONLY)
def list_indicators(tema: Optional[str] = None, nivel: Optional[str] = None) -> list[dict]:
    """Lista los indicadores del catálogo, opcionalmente filtrados por tema y nivel.

    Es el punto de entrada: devuelve una vista reducida (id, nombre, tema, nivel,
    unidad y periodicidad) para no gastar contexto cuando el catálogo crezca. La
    definición, la fuente y los parámetros de uno se piden con `describir_indicador`.

    Sin coincidencias devuelve una lista vacía, no un error.

    Args:
        tema: Tema del catálogo, por ejemplo "empleo" o "pobreza".
        nivel: Desagregación geográfica: "nacional", "estatal" o "municipal".
    """
    with _surfaced():
        return find(tema=tema, nivel=nivel)


@mcp.tool(name="describir_indicador", annotations=READ_ONLY)
def describe_indicator(id: str) -> dict:
    """Metadata completa de un indicador: definición, unidad, fuente, notas y parámetros.

    Lee `parametros[]` antes de consultar: ahí está el nombre, el tipo y si es
    requerido cada valor que acepta `consultar_indicador`.

    Args:
        id: Identificador del indicador, tal como lo devuelve `listar_indicadores`.
    """
    with _surfaced():
        return get(id).metadata()


@mcp.tool(name="consultar_indicador", annotations=READ_ONLY)
def query_indicator(id: str, parametros: Optional[dict[str, str | int | None]] = None) -> dict:
    """Consulta los datos de un indicador y los devuelve con su metadata al lado.

    Las filas vienen en formato largo con cinco columnas fijas: cve_geo, nombre_geo,
    periodo, valor y categoria. Junto a ellas viajan la unidad, la fuente y las notas,
    que son lo que evita reportar el dato sin su letra chica.

    Si la consulta excede el límite de filas falla en vez de truncar, y el error nombra
    los parámetros con los que acotar.

    Args:
        id: Identificador del indicador.
        parametros: Valores para los parámetros declarados por el indicador. Los
            opcionales que se omitan no filtran.
    """
    with _surfaced():
        return engine.execute(id, parametros)
