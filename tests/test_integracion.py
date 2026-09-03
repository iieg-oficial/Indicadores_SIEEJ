"""Los 12 indicadores contra las bases reales del piloto. **No corre en CI.**

Es la única prueba de que el catálogo sirve: que cada YAML devuelve filas, que las cinco
columnas salen en orden y que los filtros opcionales filtran de verdad. Todo lo demás se
prueba con dobles y corre en cada PR; esto necesita las cuatro bases vivas.

Se corre a mano, con `IIEGDB_PG_*` apuntando a ellas:

    pytest -m integration

Un pipeline sin DSN hace `skip`, no falla: un despliegue parcial es legítimo. Cómo y con
qué frecuencia correrlas está en docs/pruebas-integracion.md.
"""

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from indicadores_sieej import connections, engine
from indicadores_sieej.catalog import COLUMNS, load
from indicadores_sieej.config import Settings, settings

pytestmark = pytest.mark.integration

INDICATORS = list(load().values())

# Sin filtros, la serie completa de estos indicadores rebasa el límite y el motor falla
# —a propósito, en vez de truncar—. Si otro indicador empieza a rebasarlo, se acota aquí:
# es el mismo mecanismo que traía la suite del ETL.
ACOTAR = {"incidencia_delictiva_municipal": {"cve_geo": "14039"}}

# El municipio con el que se comprueba que el filtro geográfico filtra. Guadalajara.
MUNICIPIO = "14039"


@pytest.fixture(scope="session")
def cfg() -> Settings:
    """Las settings del despliegue que se está probando.

    Se salta en vez de reventar al recolectar: un `pytest` pelado en la máquina de
    alguien no tiene por qué fallar por no tener un `.env` con bases reales.
    """
    try:
        return settings()
    except ValidationError:
        pytest.skip("requiere un .env con IIEGDB_PG_* apuntando a las bases del piloto")


@pytest.fixture(params=INDICATORS, ids=lambda ind: ind.id)
def rows(request, cfg):
    ind = request.param
    if not connections.available(ind.pipeline, cfg):
        pytest.skip(f"sin DSN para el pipeline '{ind.pipeline}'")
    return engine.execute(ind.id, ACOTAR.get(ind.id, {}), cfg)["filas"]


def test_devuelve_filas(rows):
    """Un indicador que no devuelve nada es un YAML apuntando al vacío: la vista de
    origen cambió de nombre, de columnas o se quedó sin datos."""
    assert rows, "la consulta no devolvió filas"


def test_las_cinco_columnas_en_orden(rows):
    assert list(rows[0]) == list(COLUMNS)


def test_cve_geo_bien_formada(rows):
    """2 caracteres si es estatal, 5 si es municipal. Nunca nula: es la llave con la que
    se cruzan indicadores de bases distintas."""
    for row in rows:
        assert row["cve_geo"] is not None
        assert len(row["cve_geo"]) in (2, 5), row["cve_geo"]


def test_respeta_el_limite(rows, cfg):
    assert len(rows) <= cfg.row_limit


def test_el_filtro_por_municipio_filtra(cfg):
    """Que el bind opcional llegue a la base, y no se quede en el camino.

    Un filtro ignorado en silencio es peor que un error: el analista cree que está viendo
    Guadalajara y está viendo el país entero.
    """
    if not connections.available("pobreza_multidimensional", cfg):
        pytest.skip("sin DSN para el pipeline 'pobreza_multidimensional'")

    rows = engine.execute("pobreza_municipal", {"cve_geo": MUNICIPIO}, cfg)["filas"]

    assert rows
    assert {row["cve_geo"] for row in rows} == {MUNICIPIO}


@pytest.mark.parametrize("pipeline", sorted({ind.pipeline for ind in INDICATORS}))
def test_el_rol_no_puede_escribir(pipeline, cfg):
    """CA-7 contra la base, no contra el servidor: es el criterio de salida de #24.

    Falla mientras el despliegue se conecte con un rol que sí puede escribir —tu usuario
    de siempre, por ejemplo—, y eso es justo lo que tiene que decir. Con `indicadores_ro`
    creado, la escritura la rechaza `default_transaction_read_only` del rol, sin que el
    servidor tenga que pedir nada.
    """
    if not connections.available(pipeline, cfg):
        pytest.skip(f"sin DSN para el pipeline '{pipeline}'")

    with pytest.raises(SQLAlchemyError):
        with connections.pool(pipeline, cfg).connect() as conn:
            conn.execute(text("CREATE TEMP TABLE _escritura_prohibida (x int)"))
