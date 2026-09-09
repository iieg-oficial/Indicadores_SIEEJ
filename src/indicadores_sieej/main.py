"""El proceso: MCP en `/mcp` y REST en `/v1`, **un solo app ASGI**.

El montaje tiene una sola forma correcta. Si no se encadena el lifespan del app MCP, su
gestor de sesiones no se inicializa y `/mcp` no responde — sin error al arrancar, que es
lo que lo hace difícil de diagnosticar después.

Y si alguna vez hace falta CORS, va **por sub-app**, nunca como middleware global: un
`CORSMiddleware` de nivel superior sobre un servidor MCP con OAuth rompe las rutas
`.well-known` y las peticiones `OPTIONS`.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from indicadores_sieej import connections, registry
from indicadores_sieej.api import bank_error_handler, operations, public, router, schema, validation_error_handler
from indicadores_sieej.auth import AuthMiddleware
from indicadores_sieej.catalog import load
from indicadores_sieej.config import settings
from indicadores_sieej.errors import BankError
from indicadores_sieej.mcp_server import mcp

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Arma el app. Es una función y no un módulo suelto para poder montarlo en pruebas."""
    mcp_app = mcp.http_app(path="/")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Config y catálogo se validan aquí: una configuración incompleta o un YAML
        # inválido impiden arrancar, en vez de fallar al servir la primera consulta.
        cfg = settings()
        indicators = load()
        logging.getLogger().setLevel(cfg.log_level)
        if cfg.entorno == "dev":
            # Ruidoso a propósito: `sslmode=disable` es tráfico a la base **sin cifrar**,
            # y un relajamiento silencioso es el que sobrevive hasta producción.
            log.warning(
                "IIEGDB_ENTORNO=dev: sslmode=%s (sin cifrar) y base_url=%s. No usar fuera de desarrollo.",
                cfg.pg_sslmode,
                cfg.base_url,
            )
        log.info("catálogo cargado: %d indicadores", len(indicators))

        async with mcp_app.router.lifespan_context(mcp_app):
            yield

        connections.close_all()
        registry.close()

    app = FastAPI(
        title="Banco de indicadores IIEG",
        description="Catálogo curado de indicadores del IIEG. La misma funcionalidad en MCP y en REST.",
        lifespan=lifespan,
        # Los de FastAPI nacen sin dependencias; los re-registra api.py autenticados.
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Por tipo de excepción, no por el texto del mensaje: ver api.py.
    app.add_exception_handler(BankError, bank_error_handler)
    # Y el 422 de fábrica de FastAPI se traduce a 400, que es lo que docs/errores.md
    # asigna a un parámetro inválido.
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.include_router(operations)
    app.include_router(schema)
    app.include_router(router)
    # Trae una sola ruta, y sin autenticación a propósito: POST /v1/api-keys.
    app.include_router(public)
    # La misma verificación que protege /v1, envuelta como ASGI: ver auth.py.
    app.mount("/mcp", AuthMiddleware(mcp_app))
    return app


app = create_app()
