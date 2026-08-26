"""El paquete importa y su versión respeta la convención del proyecto."""

import re
import tomllib
from pathlib import Path

import indicadores_sieej

ROOT = Path(__file__).resolve().parent.parent

# vX.Y, o vX.Y.Z solo cuando hay un quick fix. El patch nunca es cero: ver docs/versionado.md.
VERSION = re.compile(r"^\d+\.\d+(\.[1-9]\d*)?$")


def test_the_package_imports():
    assert indicadores_sieej.__version__


def test_the_version_does_not_end_in_patch_zero():
    assert VERSION.fullmatch(indicadores_sieej.__version__), (
        f"'{indicadores_sieej.__version__}' no respeta la convención vX.Y / vX.Y.Z sin patch cero"
    )


def test_the_version_matches_between_pyproject_and_the_package():
    """Se desincronizan con facilidad porque el release las toca por separado."""
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == indicadores_sieej.__version__
