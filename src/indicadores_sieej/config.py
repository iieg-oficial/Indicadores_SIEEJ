"""Settings del servidor, validadas al arranque.

Una configuración inválida o incompleta **impide arrancar**, con un mensaje que
nombra la variable — no falla más tarde al servir la primera consulta.

La tabla completa de variables está en docs/configuracion.md.
"""

from functools import lru_cache
from typing import Literal, Optional

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

TODOS = "*"


class Settings(BaseSettings):
    """Las variables `IIEGDB_*`. Los `IIEGDB_DSN_<PIPELINE>` no son campos: los lee
    conexiones.py del entorno, porque su nombre depende del catálogo."""

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
    auth_mode: Literal["static", "jwt"]
    static_tokens: Optional[SecretStr] = None
    jwks_uri: Optional[str] = None
    issuer: Optional[str] = None
    audience: Optional[str] = None
    base_url: str

    # --- Límites y operación ---
    limite_filas: int = 5000
    statement_timeout_ms: int = 15000
    rate_limit: int = 60

    # Por pipeline, no globales: se multiplican por los pipelines en uso. El
    # presupuesto está en docs/conexiones.md.
    pool_size: int = 2
    pool_max_overflow: int = 3
    pool_timeout_s: int = 10

    log_level: str = "INFO"

    @model_validator(mode="after")
    def _exigir_lo_del_modo_de_auth(self) -> "Settings":
        faltantes = []
        if self.auth_mode == "static" and not self.static_tokens:
            faltantes = ["IIEGDB_STATIC_TOKENS"]
        elif self.auth_mode == "jwt":
            faltantes = [
                nombre
                for nombre, valor in (
                    ("IIEGDB_JWKS_URI", self.jwks_uri),
                    ("IIEGDB_ISSUER", self.issuer),
                    ("IIEGDB_AUDIENCE", self.audience),
                )
                if not valor
            ]
        if faltantes:
            raise ValueError(f"con IIEGDB_AUTH_MODE={self.auth_mode} falta {', '.join(faltantes)}")
        return self

    def habilita(self, pipeline: str) -> bool:
        """Si este despliegue sirve ese pipeline desde el servidor por defecto."""
        return self.pipelines.strip() == TODOS or pipeline in self.pipelines_habilitados

    @property
    def pipelines_habilitados(self) -> list[str]:
        if self.pipelines.strip() == TODOS:
            return []
        return [p.strip() for p in self.pipelines.split(",") if p.strip()]


@lru_cache(maxsize=1)
def settings() -> Settings:
    """Las settings del proceso. Se resuelven una vez y se reutilizan."""
    return Settings()
