"""Settings validadas al arranque. No requiere base de datos."""

import pytest
from pydantic import ValidationError

from indicadores_sieej.config import Settings

from .conftest import cfg as _cfg


def test_falta_una_variable_obligatoria_y_el_arranque_falla():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, pg_host="h", auth_mode="static", static_tokens="t", base_url="https://x")
    faltantes = {error["loc"][0] for error in exc.value.errors()}
    assert {"pg_user", "pg_password", "pipelines"} <= faltantes


def test_los_valores_por_defecto_son_los_documentados():
    settings = _cfg()
    assert (settings.pg_port, settings.pg_sslmode) == (5432, "require")
    assert (settings.limite_filas, settings.statement_timeout_ms, settings.rate_limit) == (5000, 15000, 60)
    assert (settings.pool_size, settings.pool_max_overflow, settings.pool_timeout_s) == (2, 3, 10)
    assert settings.log_level == "INFO"


def test_pipelines_acepta_lista_y_asterisco():
    lista = _cfg(pipelines="ilmm, enoe_microdatos ")
    assert lista.pipelines_habilitados == ["ilmm", "enoe_microdatos"]
    assert lista.habilita("ilmm") and not lista.habilita("conapo")
    assert _cfg(pipelines="*").habilita("cualquiera")


def test_el_modo_static_exige_sus_tokens():
    with pytest.raises(ValidationError, match="IIEGDB_STATIC_TOKENS"):
        _cfg(auth_mode="static", static_tokens=None)


def test_el_modo_jwt_exige_su_verificacion():
    with pytest.raises(ValidationError, match="IIEGDB_JWKS_URI, IIEGDB_ISSUER, IIEGDB_AUDIENCE"):
        _cfg(auth_mode="jwt")
    assert _cfg(auth_mode="jwt", jwks_uri="https://i/jwks", issuer="https://i/", audience="a")


def test_la_contrasena_y_los_tokens_no_salen_en_el_repr():
    settings = _cfg(pg_password="contrasena_real", static_tokens="token_real")
    texto = f"{settings!r} {settings.pg_password} {settings.static_tokens}"
    assert "contrasena_real" not in texto and "token_real" not in texto
