"""Ejecución acotada y de solo lectura. La única capa que toca la base.

Los valores viajan **siempre** como binds del driver. Está prohibido construir el SQL
concatenando cadenas o agregando cláusulas WHERE según qué parámetros llegaron: los
YAML ya resuelven los filtros opcionales con `(CAST(:param AS tipo) IS NULL OR ...)`.
Como no hay construcción dinámica, no existe superficie de inyección.

Las claves del sobre de respuesta van en español: son el contrato de
docs/superficies.md, que consumen las superficies MCP y REST.

Ver docs/garantias.md y docs/reglas-sql.md.
"""

import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from indicadores_sieej import connections
from indicadores_sieej.catalog import get
from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errors import InvalidParameters, PipelineUnavailable, QueryError, RowLimitExceeded
from indicadores_sieej.models import TYPES, Indicator

log = logging.getLogger(__name__)


def _binds(ind: Indicator, params: dict) -> dict:
    """Valida los params contra los declarados y rellena con None los ausentes.

    Un opcional ausente se manda como NULL, que es lo que neutraliza su filtro.
    """
    declared = {p.nombre: p for p in ind.parametros}

    unknown = set(params) - set(declared)
    if unknown:
        raise InvalidParameters(f"{ind.id}: parámetros desconocidos {sorted(unknown)}")

    binds = {}
    for name, param in declared.items():
        value = params.get(name)
        if value is None:
            if param.requerido:
                raise InvalidParameters(f"{ind.id}: falta el parámetro requerido '{name}'")
            binds[name] = None
        else:
            try:
                binds[name] = TYPES[param.tipo](value)
            except (TypeError, ValueError):
                raise InvalidParameters(f"{ind.id}: el parámetro '{name}' no es un {param.tipo} válido") from None
    return binds


def _bounded(ind: Indicator, limit: int):
    """Envuelve el sql del catálogo para pedir una fila de más que el límite.

    La fila extra es lo que distingue "cabe justo" de "está truncado". El sql entra
    entero y sin tocar: aquí no se arma nada con los valores del usuario.
    """
    return text(f"SELECT * FROM (\n{ind.sql.rstrip().rstrip(';')}\n) _bank LIMIT {limit + 1}")


def execute(id: str, params: Optional[dict] = None, cfg: Optional[Settings] = None) -> dict:
    """Ejecuta el indicador y devuelve el sobre de respuesta de docs/superficies.md.

    Los parámetros llegan en un diccionario y no como `**kwargs` porque sus nombres
    los pone el YAML: uno llamado `id` o `cfg` chocaría con los de esta firma, y la
    superficie REST los toma tal cual del query string.
    """
    cfg = cfg or settings()
    ind = get(id)
    binds = _binds(ind, params or {})

    if not connections.available(ind.pipeline, cfg):
        raise PipelineUnavailable(f"{ind.id}: indicador no disponible en este despliegue")

    try:
        with connections.pool(ind.pipeline, cfg).connect() as conn:
            conn = conn.execution_options(postgresql_readonly=True)
            rows = [dict(row) for row in conn.execute(_bounded(ind, cfg.row_limit), binds).mappings()]
    except SQLAlchemyError as exc:
        # Al cliente va genérico y con una referencia; el detalle, al log — y sin el
        # sql, que es lo único que nunca sale del servidor. Por eso no se registra la
        # excepción completa: su texto trae la consulta.
        reference = uuid4().hex[:8]
        log.error("consulta fallida (%s) en %s/%s: %s", reference, ind.pipeline, ind.id, type(exc).__name__)
        raise QueryError(f"{ind.id}: error al consultar la base (referencia: {reference})") from None

    # El límite falla ruidoso: devolver 5000 filas de una serie de 40000 sin decirlo
    # haría que el agente reportara como completa una serie cortada.
    if len(rows) > cfg.row_limit:
        raise RowLimitExceeded(
            f"{ind.id}: la consulta excede {cfg.row_limit} filas; acota con {sorted(p.nombre for p in ind.parametros)}"
        )

    envelope = {
        "indicador": ind.id,
        "nombre": ind.nombre,
        "unidad": ind.unidad,
        "fuente": ind.fuente,
    }
    if ind.notas:
        # La letra chica que evita que el agente afirme de más: en varias vistas de
        # origen, ausencia de fila no es cero.
        envelope["notas"] = ind.notas
    # Los opcionales van explícitos en null: hace visible que la serie no se filtró.
    envelope["parametros_aplicados"] = binds
    envelope["filas"] = rows
    return envelope
