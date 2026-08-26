"""Ejecución acotada y de solo lectura. La única capa que toca la base.

Los valores viajan **siempre** como binds del driver. Está prohibido construir el SQL
concatenando cadenas o agregando cláusulas WHERE según qué parámetros llegaron: los
YAML ya resuelven los filtros opcionales con `(CAST(:param AS tipo) IS NULL OR ...)`.
Como no hay construcción dinámica, no existe superficie de inyección.

Ver docs/garantias.md y docs/reglas-sql.md.
"""

import logging
from typing import Optional
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from indicadores_sieej import conexiones
from indicadores_sieej.catalogo import obtener
from indicadores_sieej.config import Settings, settings
from indicadores_sieej.errores import ErrorDeConsulta, LimiteExcedido, ParametrosInvalidos, PipelineNoDisponible
from indicadores_sieej.models import TYPES, Indicator

log = logging.getLogger(__name__)


def _binds(ind: Indicator, params: dict) -> dict:
    """Valida los params contra los declarados y rellena con None los ausentes.

    Un opcional ausente se manda como NULL, que es lo que neutraliza su filtro.
    """
    declarados = {p.nombre: p for p in ind.parametros}

    desconocidos = set(params) - set(declarados)
    if desconocidos:
        raise ParametrosInvalidos(f"{ind.id}: parámetros desconocidos {sorted(desconocidos)}")

    binds = {}
    for nombre, param in declarados.items():
        valor = params.get(nombre)
        if valor is None:
            if param.requerido:
                raise ParametrosInvalidos(f"{ind.id}: falta el parámetro requerido '{nombre}'")
            binds[nombre] = None
        else:
            try:
                binds[nombre] = TYPES[param.tipo](valor)
            except (TypeError, ValueError):
                raise ParametrosInvalidos(f"{ind.id}: el parámetro '{nombre}' no es un {param.tipo} válido") from None
    return binds


def _acotada(ind: Indicator, limite: int):
    """Envuelve el sql del catálogo para pedir una fila de más que el límite.

    La fila extra es lo que distingue "cabe justo" de "está truncado". El sql entra
    entero y sin tocar: aquí no se arma nada con los valores del usuario.
    """
    return text(f"SELECT * FROM (\n{ind.sql.rstrip().rstrip(';')}\n) _banco LIMIT {limite + 1}")


def ejecutar(id: str, cfg: Optional[Settings] = None, **params) -> dict:
    """Ejecuta el indicador y devuelve el sobre de respuesta de docs/superficies.md."""
    cfg = cfg or settings()
    ind = obtener(id)
    binds = _binds(ind, params)

    if not conexiones.disponible(ind.pipeline, cfg):
        raise PipelineNoDisponible(f"{ind.id}: indicador no disponible en este despliegue")

    try:
        with conexiones.pool(ind.pipeline, cfg).connect() as conn:
            conn = conn.execution_options(postgresql_readonly=True)
            filas = [dict(fila) for fila in conn.execute(_acotada(ind, cfg.limite_filas), binds).mappings()]
    except SQLAlchemyError as exc:
        # Al cliente va genérico y con una referencia; el detalle, al log — y sin el
        # sql, que es lo único que nunca sale del servidor. Por eso no se registra la
        # excepción completa: su texto trae la consulta.
        referencia = uuid4().hex[:8]
        log.error("consulta fallida (%s) en %s/%s: %s", referencia, ind.pipeline, ind.id, type(exc).__name__)
        raise ErrorDeConsulta(f"{ind.id}: error al consultar la base (referencia: {referencia})") from None

    # El límite falla ruidoso: devolver 5000 filas de una serie de 40000 sin decirlo
    # haría que el agente reportara como completa una serie cortada.
    if len(filas) > cfg.limite_filas:
        raise LimiteExcedido(
            f"{ind.id}: la consulta excede {cfg.limite_filas} filas; "
            f"acota con {sorted(p.nombre for p in ind.parametros)}"
        )

    sobre = {
        "indicador": ind.id,
        "nombre": ind.nombre,
        "unidad": ind.unidad,
        "fuente": ind.fuente,
    }
    if ind.notas:
        # La letra chica que evita que el agente afirme de más: en varias vistas de
        # origen, ausencia de fila no es cero.
        sobre["notas"] = ind.notas
    # Los opcionales van explícitos en null: hace visible que la serie no se filtró.
    sobre["parametros_aplicados"] = binds
    sobre["filas"] = filas
    return sobre
