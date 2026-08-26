"""Carga y validación del catálogo. No requiere base de datos.

Las pruebas sobre los indicadores reales van parametrizadas: agregar un YAML al
catálogo las extiende solo. Las de las siete validaciones arman un catálogo de
mentira en un directorio temporal a partir de un indicador real.
"""

from pathlib import Path

import pytest
import yaml

from indicadores_sieej.catalogo import BINDS, CATALOGO, COLUMNAS, VISTA_REDUCIDA, cargar, listar, obtener
from indicadores_sieej.errores import CatalogoInvalido, IndicadorNoExiste

INDICADORES = list(cargar().values())

# Punto de partida de las pruebas negativas: un indicador válido al que se le rompe
# una cosa a la vez.
BASE = yaml.safe_load((CATALOGO / "pobreza" / "pobreza_municipal.yaml").read_text(encoding="utf-8"))


def _catalogo(raiz: Path, carpeta: str = "pobreza", archivo: str = "pobreza_municipal", **cambios) -> Path:
    destino = raiz / carpeta
    destino.mkdir(parents=True, exist_ok=True)
    contenido = yaml.safe_dump({**BASE, **cambios}, allow_unicode=True, sort_keys=False)
    (destino / f"{archivo}.yaml").write_text(contenido, encoding="utf-8")
    return raiz


# --- Los indicadores del catálogo real ---


def test_catalogo_no_vacio():
    assert INDICADORES, "el catálogo no cargó ningún indicador"


def test_ids_unicos():
    # cargar() ya revienta con ids duplicados; esto ancla la garantía.
    ids = [ind.id for ind in INDICADORES]
    assert len(ids) == len(set(ids))


def test_id_coincide_con_nombre_de_archivo():
    for ruta in CATALOGO.glob("*/*.yaml"):
        assert ruta.stem in cargar(), f"{ruta}: el id no coincide con el nombre del archivo"


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_tema_coincide_con_carpeta(ind):
    assert (CATALOGO / ind.tema / f"{ind.id}.yaml").exists()


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_sql_es_de_solo_lectura(ind):
    assert ind.sql.lstrip().upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_parametros_y_binds_coinciden(ind):
    assert {p.nombre for p in ind.parametros} == set(BINDS.findall(ind.sql))


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_sql_declara_las_cinco_columnas(ind):
    for columna in COLUMNAS:
        assert f"AS {columna}" in ind.sql, f"{ind.id}: falta la columna '{columna}' en el SELECT"


def test_listar_filtra_y_devuelve_la_vista_reducida():
    empleo = listar(tema="empleo")
    assert empleo and all(m["tema"] == "empleo" for m in empleo)
    assert all(set(m) == set(VISTA_REDUCIDA) for m in empleo)
    assert all(m["nivel"] == "municipal" for m in listar(nivel="municipal"))
    assert listar(tema="no_existe") == []


def test_obtener_devuelve_la_metadata_completa_sin_sql():
    metadata = obtener("pobreza_municipal").metadata()
    assert "sql" not in metadata
    assert metadata["definicion"] and metadata["fuente"] and metadata["parametros"]


def test_obtener_id_inexistente():
    with pytest.raises(IndicadorNoExiste):
        obtener("no_existe")


def test_binds_ignora_los_casts_de_postgres():
    assert BINDS.findall("valor::numeric = CAST(:cve_geo AS text)") == ["cve_geo"]


# --- Las siete validaciones, una prueba por mensaje ---


def test_campo_desconocido(tmp_path):
    raiz = _catalogo(tmp_path, inventado="lo que sea")
    with pytest.raises(CatalogoInvalido, match="campo desconocido 'inventado'"):
        cargar(raiz)


def test_id_duplicado(tmp_path):
    # Los dos archivos son válidos por separado: mismo nombre, cada uno en su tema.
    _catalogo(tmp_path, carpeta="empleo", tema="empleo")
    _catalogo(tmp_path)
    with pytest.raises(CatalogoInvalido, match="id duplicado 'pobreza_municipal'"):
        cargar(tmp_path)


def test_id_distinto_del_nombre_de_archivo(tmp_path):
    raiz = _catalogo(tmp_path, archivo="otro_nombre")
    with pytest.raises(CatalogoInvalido, match="el id no coincide con el nombre del archivo"):
        cargar(raiz)


def test_tema_distinto_de_la_carpeta(tmp_path):
    raiz = _catalogo(tmp_path, carpeta="empleo")
    with pytest.raises(CatalogoInvalido, match="el tema no coincide con la carpeta"):
        cargar(raiz)


def test_sql_que_no_empieza_con_select(tmp_path):
    raiz = _catalogo(tmp_path, sql="UPDATE vw_pobreza SET valor = 0")
    with pytest.raises(CatalogoInvalido, match="el sql debe empezar con SELECT o WITH"):
        cargar(raiz)


def test_sql_sin_las_cinco_columnas(tmp_path):
    raiz = _catalogo(tmp_path, sql="SELECT 1 AS cve_geo", parametros=[])
    with pytest.raises(CatalogoInvalido, match=r"el sql no proyecta las columnas \['nombre_geo'"):
        cargar(raiz)


def test_desajuste_entre_parametros_y_binds(tmp_path):
    # El sql usa :cve_geo y :anio_min; se declara solo el primero.
    raiz = _catalogo(tmp_path, parametros=BASE["parametros"][:1])
    with pytest.raises(CatalogoInvalido, match=r"usados sin declarar: \['anio_min'\]"):
        cargar(raiz)
