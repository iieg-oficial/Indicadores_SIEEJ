"""Carga y validación del catálogo. Sin base de datos: aquí solo se leen YAML.

El catálogo se carga y valida **una sola vez, al arrancar el proceso**. Un catálogo
inválido impide el arranque con un mensaje que nombra el archivo y la falla; nunca
degrada en un error servido al usuario en producción.

Las siete validaciones y sus mensajes exactos están en docs/validaciones-catalogo.md.
"""

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import ValidationError

from indicadores_sieej.errores import CatalogoInvalido, IndicadorNoExiste
from indicadores_sieej.modelo import Indicador

# El catálogo vive en la raíz del repositorio, no junto al módulo como en el ETL.
CATALOGO = Path(__file__).resolve().parents[2] / "catalogo"

COLUMNAS = ("cve_geo", "nombre_geo", "periodo", "valor", "categoria")

# Binds de SQLAlchemy (:param) ignorando los casts de PostgreSQL (valor::numeric).
# Sin el lookbehind, `valor::numeric` se lee como un bind llamado `numeric` y toda la
# validación de parámetros da falsos positivos.
BINDS = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")


def _falla(exc: ValidationError) -> str:
    """Traduce el error de pydantic al mensaje de la tabla de validaciones."""
    for error in exc.errors():
        if error["type"] == "extra_forbidden":
            return f"campo desconocido '{error['loc'][-1]}'"
    error = exc.errors()[0]
    campo = ".".join(str(parte) for parte in error["loc"])
    return f"campo '{campo}': {error['msg']}"


def _leer(ruta: Path) -> Indicador:
    """Primera validación: valida contra el modelo, sin campos extra."""
    try:
        datos = yaml.safe_load(ruta.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise CatalogoInvalido(f"{ruta}: el YAML está mal formado") from None
    if not isinstance(datos, dict):
        raise CatalogoInvalido(f"{ruta}: el YAML no describe un indicador")
    try:
        return Indicador(**datos)
    except ValidationError as exc:
        raise CatalogoInvalido(f"{ruta}: {_falla(exc)}") from None


def _validar(ind: Indicador, ruta: Path) -> None:
    """Las validaciones que no dependen del modelo.

    El `pipeline` **no** se valida aquí: que su base esté configurada en este
    despliegue es operación, no catálogo. Un pipeline sin conexión resuelta no impide
    arrancar; sus indicadores responden 503. Ver docs/conexiones.md.
    """
    if ruta.stem != ind.id:
        raise CatalogoInvalido(f"{ruta}: el id no coincide con el nombre del archivo")

    if ruta.parent.name != ind.tema:
        raise CatalogoInvalido(f"{ruta}: el tema no coincide con la carpeta")

    if not ind.sql.lstrip().upper().startswith(("SELECT", "WITH")):
        raise CatalogoInvalido(f"{ruta}: el sql debe empezar con SELECT o WITH")

    faltantes = [col for col in COLUMNAS if f"AS {col}" not in ind.sql]
    if faltantes:
        raise CatalogoInvalido(f"{ruta}: el sql no proyecta las columnas {faltantes}")

    declarados = {p.nombre for p in ind.parametros}
    usados = set(BINDS.findall(ind.sql))
    if declarados != usados:
        raise CatalogoInvalido(
            f"{ruta}: desajuste entre parametros y binds del sql "
            f"(declarados sin usar: {sorted(declarados - usados)}, "
            f"usados sin declarar: {sorted(usados - declarados)})"
        )


@lru_cache(maxsize=None)
def cargar(raiz: Path = CATALOGO) -> dict[str, Indicador]:
    """Carga y valida todo el catálogo. Cualquier falla revienta aquí, al arrancar."""
    if not raiz.is_dir():
        raise CatalogoInvalido(f"{raiz}: no existe el directorio del catálogo")

    indicadores: dict[str, Indicador] = {}
    for ruta in sorted(raiz.glob("*/*.yaml")):
        ind = _leer(ruta)
        if ind.id in indicadores:
            raise CatalogoInvalido(f"{ruta}: id duplicado '{ind.id}'")
        _validar(ind, ruta)
        indicadores[ind.id] = ind
    return indicadores


def listar(tema: Optional[str] = None, nivel: Optional[str] = None) -> list[dict]:
    """Metadata de los indicadores (sin el sql), filtrable por tema y nivel."""
    return [
        ind.metadata()
        for ind in cargar().values()
        if (tema is None or ind.tema == tema) and (nivel is None or ind.nivel == nivel)
    ]


def obtener(id: str) -> Indicador:
    try:
        return cargar()[id]
    except KeyError:
        raise IndicadorNoExiste(f"Indicador '{id}' no existe en el catálogo") from None
