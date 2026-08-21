"""El paquete importa y sus tres declaraciones de versión coinciden."""

import json
import tomllib
from pathlib import Path

import indicadores_sieej

RAIZ = Path(__file__).resolve().parent.parent


def test_el_paquete_importa():
    assert indicadores_sieej.__version__


def test_la_version_es_la_misma_en_los_tres_lugares():
    """pyproject, el manifest de release-please y __init__ se desincronizan con facilidad."""
    pyproject = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = json.loads((RAIZ / ".release-please-manifest.json").read_text(encoding="utf-8"))

    assert pyproject["project"]["version"] == indicadores_sieej.__version__
    assert manifest["."] == indicadores_sieej.__version__
