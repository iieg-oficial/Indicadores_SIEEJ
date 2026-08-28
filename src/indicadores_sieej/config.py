"""Settings del servidor, validadas al arranque.

Una configuración inválida o incompleta **impide arrancar**, con un mensaje que
nombra la variable — no falla más tarde al servir la primera consulta.

La tabla completa de variables está en docs/configuracion.md.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ALL = "*"


class Settings(BaseSettings):
    """Las variables `IIEGDB_*`. Los `IIEGDB_DSN_<PIPELINE>` no son campos: los lee
    connections.py del entorno, porque su nombre depende del catálogo."""

    model_config = SettingsConfigDict(env_prefix="IIEGDB_", env_file=".env", extra="ignore")

    # --- Servidor por defecto ---
    pg_host: str
    pg_port: int = 5432
    pg_user: str
    pg_password: SecretStr
    pg_sslmode: str = "require"

    # Se declara como texto y se parte a mano: si fuera list[str], pydantic-settings
    # esperaría un JSON en la variable de entorno, no una lista separada por comas.
    pipelines: str

    # --- Autenticación ---
    # `api_key` es el modo de producción: API keys de autoservicio verificadas contra la
    # base propia del servicio. `static` es para desarrollo; `jwt`, para el día que haya
    # un proveedor de identidad institucional. Los tres nombran **qué credencial** se
    # verifica, no dónde se guarda. Decidido en #29.
    auth_mode: Literal["static", "jwt", "api_key"]
    static_tokens: Optional[SecretStr] = None
    jwks_uri: Optional[str] = None
    issuer: Optional[str] = None
    audience: Optional[str] = None
    base_url: str

    # DSN propio y rol propio, **nunca derivado de IIEGDB_PG_***: ese bloque es el rol de
    # solo lectura de las 33 bases del ETL, y derivar de ahí crearía presión para darle
    # permisos de escritura. Eso rompería la garantía de solo lectura en todas a la vez.
    registry_dsn: Optional[SecretStr] = None

    # Las tres ventanas del registro de API keys. Ver docs/api-keys.md.
    api_key_ttl_days: int = 90
    api_key_touch_s: int = 3600
    api_key_cache_ttl_s: int = 60

    # --- Límites y operación ---
    row_limit: int = 5000
    statement_timeout_ms: int = 15000
    rate_limit: int = 60

    # Por pipeline, no globales: se multiplican por los pipelines en uso. El
    # presupuesto está en docs/conexiones.md.
    pool_size: int = 2
    pool_max_overflow: int = 3
    pool_timeout_s: int = 10

    log_level: str = "INFO"

    @model_validator(mode="after")
    def _require_auth_mode_fields(self) -> "Settings":
        missing = []
        if self.auth_mode == "static" and not self.static_tokens:
            missing = ["IIEGDB_STATIC_TOKENS"]
        elif self.auth_mode == "jwt":
            missing = [
                name
                for name, value in (
                    ("IIEGDB_JWKS_URI", self.jwks_uri),
                    ("IIEGDB_ISSUER", self.issuer),
                    ("IIEGDB_AUDIENCE", self.audience),
                )
                if not value
            ]
        elif self.auth_mode == "api_key" and not self.registry_dsn:
            missing = ["IIEGDB_REGISTRY_DSN"]
        if missing:
            raise ValueError(f"con IIEGDB_AUTH_MODE={self.auth_mode} falta {', '.join(missing)}")
        return self

    @model_validator(mode="after")
    def _coherent_api_key_windows(self) -> "Settings":
        """El orden de las tres ventanas es lo que hace correcta la caducidad por desuso.

        Una key en uso refresca su `last_used_at` porque el caché expira antes que la
        ventana de refresco, y esa antes que la de caducidad. Invertir el orden —subir el
        caché "para bajar carga", por ejemplo— haría que una key en uso continuo caducara
        sola, y tardaría noventa días en notarse. Por eso se falla al arrancar.
        """
        if not self.api_key_cache_ttl_s < self.api_key_touch_s < self.api_key_ttl_days * 86400:
            raise ValueError(
                "las ventanas del registro deben cumplir "
                "IIEGDB_API_KEY_CACHE_TTL_S < IIEGDB_API_KEY_TOUCH_S < IIEGDB_API_KEY_TTL_DAYS en segundos"
            )
        return self

    def serves(self, pipeline: str) -> bool:
        """Si este despliegue sirve ese pipeline desde el servidor por defecto."""
        return self.pipelines.strip() == ALL or pipeline in self.enabled_pipelines

    @property
    def enabled_pipelines(self) -> list[str]:
        if self.pipelines.strip() == ALL:
            return []
        return [p.strip() for p in self.pipelines.split(",") if p.strip()]


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Las settings del proceso. Se resuelven una vez y se reutilizan."""
    return Settings()
