"""Jerarquía de excepciones del banco: una por fila de la tabla de docs/errores.md.

La implementación de referencia del ETL usa un único `ValueError` para todo, lo que
obliga a inspeccionar el texto del mensaje para decidir el código HTTP. Con dos
superficies —MCP y REST— eso no escala: cada una traduce por tipo, nunca por cadena.

Los mensajes de los errores recuperables llegan al agente **íntegros**: la lista de
parámetros que traen es justamente lo que le permite reintentar bien.
"""


class BankError(Exception):
    """Base común.

    `http` es el código con el que la excepción sale a la superficie. `recoverable`
    dice si el agente puede corregirse solo con lo que trae el mensaje; los no
    recuperables no llevan SQL, DSN, credenciales ni nombres de tabla.
    """

    http = 500
    recoverable = False


class IndicatorNotFound(BankError):
    """El `id` no está en el catálogo. El agente vuelve a `listar_indicadores`."""

    http = 404
    recoverable = True


class InvalidParameters(BankError):
    """Parámetro no declarado, requerido ausente, o valor no coaccionable al tipo."""

    http = 400
    recoverable = True


class RowLimitExceeded(BankError):
    """La consulta rebasa el límite de filas.

    El mensaje nombra los parámetros con los que acotar: sin esa lista el error deja
    de ser accionable y el agente no sabe cómo reintentar.
    """

    http = 413
    recoverable = True


class PipelineUnavailable(BankError):
    """El pipeline no tiene DSN resuelto en este despliegue.

    Es configuración, no catálogo: el YAML es válido y el servidor arranca igual.
    """

    http = 503
    recoverable = False


class Unauthenticated(BankError):
    """Sin token, o con un token que no verifica.

    El mensaje no dice cuál de las dos cosas pasó más allá de lo que ya distinguen el
    401 y el 403: quien prueba tokens no debe aprender nada del texto.
    """

    http = 401
    recoverable = False


class InsufficientScope(BankError):
    """Token válido, pero sin el scope que exige el banco."""

    http = 403
    recoverable = False


class RegistryUnavailable(BankError):
    """El registro de API keys no responde, o no está configurado.

    **Nunca 401.** Un 401 le diría a cada consumidor que su credencial es mala y los
    mandaría a todos a pedir una nueva, convirtiendo un parpadeo del registro en una
    estampida contra el registro. 503 dice lo que pasa: no es la key, es el servidor.
    """

    http = 503
    recoverable = False


class RateLimited(BankError):
    """Demasiadas solicitudes desde el mismo origen.

    Hoy solo la levanta la emisión de API keys, que es la única ruta pública de escritura
    del servidor. El mensaje no dice cuál de los dos topes se alcanzó —el de la IP o el
    del servidor— porque de eso solo aprendería quien está probando cuánto aguanta.
    """

    http = 429
    recoverable = False


class QueryError(BankError):
    """Base caída o consulta fallida. Al cliente va genérico; el detalle, al log."""

    http = 502
    recoverable = False


class InvalidCatalog(BankError):
    """Un YAML del catálogo no pasa alguna de las siete validaciones.

    Nunca viaja a un cliente: se levanta al cargar el catálogo e **impide el
    arranque**. Está aquí para que el CLI y las pruebas la atrapen por tipo.
    """

    http = 500
    recoverable = False
