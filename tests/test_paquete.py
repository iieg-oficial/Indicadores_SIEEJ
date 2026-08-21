"""El paquete importa y su versión respeta la convención del proyecto."""

import re
import tomllib
from pathlib import Path

import indicadores_sieej

RAIZ = Path(__file__).resolve().parent.parent

# vX.Y, o vX.Y.Z solo cuando hay un quick fix. El patch nunca es cero: ver docs/versionado.md.
VERSION = re.compile(r"^\d+\.\d+(\.[1-9]\d*)?$")


def test_el_paquete_importa():
    assert indicadores_sieej.__version__


def test_la_version_no_termina_en_patch_cero():
    assert VERSION.fullmatch(indicadores_sieej.__version__), (
        f"'{indicadores_sieej.__version__}' no respeta la convención vX.Y / vX.Y.Z sin patch cero"
    )


def test_la_version_es_la_misma_en_pyproject_y_en_el_paquete():
    """Se desincronizan con facilidad porque el release las toca por separado."""
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == indicadores_sieej.__version__
