"""Carga y validación del catálogo. Sin base de datos: aquí solo se leen YAML.

El catálogo se carga y valida **una sola vez, al arrancar el proceso**. Un catálogo
inválido impide el arranque con un mensaje que nombra el archivo y la falla; nunca
degrada en un error servido al usuario en producción.

Las siete validaciones y sus mensajes exactos están en docs/validaciones-catalogo.md.
Los mensajes van en español a propósito: son el texto tabulado en esa documentación.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from indicadores_sieej.errors import IndicatorNotFound, InvalidCatalog
from indicadores_sieej.models import Indicator

# El catálogo vive en la raíz del repositorio, no junto al módulo como en el ETL.
CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalogo"

# Las cinco columnas del formato largo. Van en español porque son el contrato de
# datos compartido con ETL-SIEEJ, no vocabulario de este código.
COLUMNS = ("cve_geo", "nombre_geo", "periodo", "valor", "categoria")

# find() es el descubrimiento: devuelve una vista reducida para no quemar tokens del
# agente cuando el catálogo crezca. La metadata completa la da get().
SUMMARY_FIELDS = ("id", "nombre", "tema", "nivel", "unidad", "periodicidad")

# Binds de SQLAlchemy (:param) ignorando los casts de PostgreSQL (valor::numeric).
# Sin el lookbehind, `valor::numeric` se lee como un bind llamado `numeric` y toda la
# validación de parámetros da falsos positivos.
BINDS = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def _message(exc: ValidationError) -> str:
    """Traduce el error de pydantic al mensaje de la tabla de validaciones."""
    for error in exc.errors():
        if error["type"] == "extra_forbidden":
            return f"campo desconocido '{error['loc'][-1]}'"
    error = exc.errors()[0]
    field = ".".join(str(part) for part in error["loc"])
    return f"campo '{field}': {error['msg']}"


def _read(path: Path) -> Indicator:
    """Primera validación: valida contra el modelo, sin campos extra."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise InvalidCatalog(f"{path}: el YAML está mal formado") from None
    if not isinstance(data, dict):
        raise InvalidCatalog(f"{path}: el YAML no describe un indicador")
    try:
        return Indicator(**data)
    except ValidationError as exc:
        raise InvalidCatalog(f"{path}: {_message(exc)}") from None


def _validate(ind: Indicator, path: Path) -> None:
    """Las validaciones que no dependen del modelo.

    El `pipeline` **no** se valida aquí: que su base esté configurada en este
    despliegue es operación, no catálogo. Un pipeline sin conexión resuelta no impide
    arrancar; sus indicadores responden 503. Ver docs/conexiones.md.
    """
    if path.stem != ind.id:
        raise InvalidCatalog(f"{path}: el id no coincide con el nombre del archivo")

    if path.parent.name != ind.tema:
        raise InvalidCatalog(f"{path}: el tema no coincide con la carpeta")

    if not ind.sql.lstrip().upper().startswith(("SELECT", "WITH")):
        raise InvalidCatalog(f"{path}: el sql debe empezar con SELECT o WITH")

    missing = [col for col in COLUMNS if f"AS {col}" not in ind.sql]
    if missing:
        raise InvalidCatalog(f"{path}: el sql no proyecta las columnas {missing}")

    declared = {p.nombre for p in ind.parametros}
    used = set(BINDS.findall(ind.sql))
    if declared != used:
        raise InvalidCatalog(
            f"{path}: desajuste entre parametros y binds del sql "
            f"(declarados sin usar: {sorted(declared - used)}, "
            f"usados sin declarar: {sorted(used - declared)})"
        )


@lru_cache(maxsize=None)
def load(root: Path = CATALOG_DIR) -> dict[str, Indicator]:
    """Carga y valida todo el catálogo. Cualquier falla revienta aquí, al arrancar."""
    if not root.is_dir():
        raise InvalidCatalog(f"{root}: no existe el directorio del catálogo")

    indicators: dict[str, Indicator] = {}
    for path in sorted(root.glob("*/*.yaml")):
        ind = _read(path)
        if ind.id in indicators:
            raise InvalidCatalog(f"{path}: id duplicado '{ind.id}'")
        _validate(ind, path)
        indicators[ind.id] = ind
    return indicators


def find(tema: Optional[str] = None, nivel: Optional[str] = None) -> list[dict]:
    """Vista reducida de los indicadores, filtrable por tema y nivel.

    Los nombres de los filtros son los campos del YAML, por eso siguen en español.
    Sin coincidencias devuelve lista vacía, no un error.
    """
    return [
        {field: getattr(ind, field) for field in SUMMARY_FIELDS}
        for ind in load().values()
        if (tema is None or ind.tema == tema) and (nivel is None or ind.nivel == nivel)
    ]


def get(id: str) -> Indicator:
    try:
        return load()[id]
    except KeyError:
        raise IndicatorNotFound(f"Indicador '{id}' no existe en el catálogo") from None
