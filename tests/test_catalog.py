"""Carga y validación del catálogo. No requiere base de datos.

Las pruebas sobre los indicadores reales van parametrizadas: agregar un YAML al
catálogo las extiende solo. Las de las siete validaciones arman un catálogo de
mentira en un directorio temporal a partir de un indicador real.
"""

from pathlib import Path

import pytest
import yaml

from indicadores_sieej.catalog import BINDS, CATALOG_DIR, COLUMNS, SUMMARY_FIELDS, find, get, load
from indicadores_sieej.errors import IndicatorNotFound, InvalidCatalog

INDICATORS = list(load().values())

# Punto de partida de las pruebas negativas: un indicador válido al que se le rompe
# una cosa a la vez.
BASE = yaml.safe_load((CATALOG_DIR / "pobreza" / "pobreza_municipal.yaml").read_text(encoding="utf-8"))


def _catalog(root: Path, folder: str = "pobreza", filename: str = "pobreza_municipal", **overrides) -> Path:
    target = root / folder
    target.mkdir(parents=True, exist_ok=True)
    content = yaml.safe_dump({**BASE, **overrides}, allow_unicode=True, sort_keys=False)
    (target / f"{filename}.yaml").write_text(content, encoding="utf-8")
    return root


# --- Los indicadores del catálogo real ---


def test_catalog_is_not_empty():
    assert INDICATORS, "el catálogo no cargó ningún indicador"


def test_ids_are_unique():
    # load() ya revienta con ids duplicados; esto ancla la garantía.
    ids = [ind.id for ind in INDICATORS]
    assert len(ids) == len(set(ids))


def test_id_matches_filename():
    for path in CATALOG_DIR.glob("*/*.yaml"):
        assert path.stem in load(), f"{path}: el id no coincide con el nombre del archivo"


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_tema_matches_folder(ind):
    assert (CATALOG_DIR / ind.tema / f"{ind.id}.yaml").exists()


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_sql_is_read_only(ind):
    assert ind.sql.lstrip().upper().startswith(("SELECT", "WITH"))


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_declared_params_match_sql_binds(ind):
    assert {p.nombre for p in ind.parametros} == set(BINDS.findall(ind.sql))


@pytest.mark.parametrize("ind", INDICATORS, ids=lambda i: i.id)
def test_sql_projects_the_five_columns(ind):
    for column in COLUMNS:
        assert f"AS {column}" in ind.sql, f"{ind.id}: falta la columna '{column}' en el SELECT"


def test_find_filters_and_returns_the_summary_view():
    empleo = find(tema="empleo")
    assert empleo and all(m["tema"] == "empleo" for m in empleo)
    assert all(set(m) == set(SUMMARY_FIELDS) for m in empleo)
    assert all(m["nivel"] == "municipal" for m in find(nivel="municipal"))
    assert find(tema="no_existe") == []


def test_get_returns_the_full_metadata_without_sql():
    metadata = get("pobreza_municipal").metadata()
    assert "sql" not in metadata
    assert metadata["definicion"] and metadata["fuente"] and metadata["parametros"]


def test_get_with_an_unknown_id():
    with pytest.raises(IndicatorNotFound):
        get("no_existe")


def test_binds_ignores_postgres_casts():
    assert BINDS.findall("valor::numeric = CAST(:cve_geo AS text)") == ["cve_geo"]


# --- El catálogo entero ---


def test_an_empty_directory_is_not_a_valid_catalog(tmp_path):
    """Cero indicadores no es un catálogo sano al que nadie catalogó nada: es un
    despliegue al que el catálogo no llegó."""
    with pytest.raises(InvalidCatalog) as exc:
        load(tmp_path)
    assert str(tmp_path) in str(exc.value), "el error tiene que nombrar el directorio"


def test_a_directory_with_folders_but_no_yaml_is_not_valid_either(tmp_path):
    (tmp_path / "pobreza").mkdir()
    with pytest.raises(InvalidCatalog):
        load(tmp_path)


# --- Las siete validaciones, una prueba por mensaje ---


def test_unknown_field(tmp_path):
    root = _catalog(tmp_path, inventado="lo que sea")
    with pytest.raises(InvalidCatalog, match="campo desconocido 'inventado'"):
        load(root)


def test_duplicate_id(tmp_path):
    # Los dos archivos son válidos por separado: mismo nombre, cada uno en su tema.
    _catalog(tmp_path, folder="empleo", tema="empleo")
    _catalog(tmp_path)
    with pytest.raises(InvalidCatalog, match="id duplicado 'pobreza_municipal'"):
        load(tmp_path)


def test_id_differs_from_filename(tmp_path):
    root = _catalog(tmp_path, filename="otro_nombre")
    with pytest.raises(InvalidCatalog, match="el id no coincide con el nombre del archivo"):
        load(root)


def test_tema_differs_from_folder(tmp_path):
    root = _catalog(tmp_path, folder="empleo")
    with pytest.raises(InvalidCatalog, match="el tema no coincide con la carpeta"):
        load(root)


def test_sql_not_starting_with_select(tmp_path):
    root = _catalog(tmp_path, sql="UPDATE vw_pobreza SET valor = 0")
    with pytest.raises(InvalidCatalog, match="el sql debe empezar con SELECT o WITH"):
        load(root)


def test_sql_without_the_five_columns(tmp_path):
    root = _catalog(tmp_path, sql="SELECT 1 AS cve_geo", parametros=[])
    with pytest.raises(InvalidCatalog, match=r"el sql no proyecta las columnas \['nombre_geo'"):
        load(root)


def test_mismatch_between_params_and_binds(tmp_path):
    # El sql usa :cve_geo y :anio_min; se declara solo el primero.
    root = _catalog(tmp_path, parametros=BASE["parametros"][:1])
    with pytest.raises(InvalidCatalog, match=r"usados sin declarar: \['anio_min'\]"):
        load(root)
