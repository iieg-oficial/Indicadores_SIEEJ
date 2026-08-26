"""Jerarquía de excepciones del banco: una por fila de la tabla de docs/errores.md.

La implementación de referencia del ETL usa un único `ValueError` para todo, lo que
obliga a inspeccionar el texto del mensaje para decidir el código HTTP. Con dos
superficies —MCP y REST— eso no escala: cada una traduce por tipo, nunca por cadena.

Los mensajes de los errores recuperables llegan al agente **íntegros**: la lista de
parámetros que traen es justamente lo que le permite reintentar bien.
"""


class ErrorDelBanco(Exception):
    """Base común.

    `http` es el código con el que la excepción sale a la superficie. `recuperable`
    dice si el agente puede corregirse solo con lo que trae el mensaje; los no
    recuperables no llevan SQL, DSN, credenciales ni nombres de tabla.
    """

    http = 500
    recuperable = False


class IndicadorNoExiste(ErrorDelBanco):
    """El `id` no está en el catálogo. El agente vuelve a `listar_indicadores`."""

    http = 404
    recuperable = True


class ParametrosInvalidos(ErrorDelBanco):
    """Parámetro no declarado, requerido ausente, o valor no coaccionable al tipo."""

    http = 400
    recuperable = True


class LimiteExcedido(ErrorDelBanco):
    """La consulta rebasa el límite de filas.

    El mensaje nombra los parámetros con los que acotar: sin esa lista el error deja
    de ser accionable y el agente no sabe cómo reintentar.
    """

    http = 413
    recuperable = True


class PipelineNoDisponible(ErrorDelBanco):
    """El pipeline no tiene DSN resuelto en este despliegue.

    Es configuración, no catálogo: el YAML es válido y el servidor arranca igual.
    """

    http = 503
    recuperable = False


class ErrorDeConsulta(ErrorDelBanco):
    """Base caída o consulta fallida. Al cliente va genérico; el detalle, al log."""

    http = 502
    recuperable = False


class CatalogoInvalido(ErrorDelBanco):
    """Un YAML del catálogo no pasa alguna de las siete validaciones.

    Nunca viaja a un cliente: se levanta al cargar el catálogo e **impide el
    arranque**. Está aquí para que el CLI y las pruebas la atrapen por tipo.
    """

    http = 500
    recuperable = False
