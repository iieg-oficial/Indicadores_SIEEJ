"""Settings validadas al arranque. No requiere base de datos."""

import pytest
from pydantic import ValidationError

from indicadores_sieej.config import Settings

from .conftest import cfg as _cfg


def test_a_missing_required_variable_blocks_startup():
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, pg_host="h", auth_mode="static", static_tokens="t", base_url="https://x")
    missing = {error["loc"][0] for error in exc.value.errors()}
    assert {"pg_user", "pg_password", "pipelines"} <= missing


def test_the_defaults_are_the_documented_ones():
    cfg = _cfg()
    assert (cfg.pg_port, cfg.pg_sslmode) == (5432, "require")
    assert (cfg.row_limit, cfg.statement_timeout_ms, cfg.rate_limit) == (5000, 15000, 60)
    assert (cfg.pool_size, cfg.pool_max_overflow, cfg.pool_timeout_s) == (2, 3, 10)
    assert cfg.log_level == "INFO"


def test_pipelines_accepts_a_list_and_an_asterisk():
    listed = _cfg(pipelines="ilmm, enoe_microdatos ")
    assert listed.enabled_pipelines == ["ilmm", "enoe_microdatos"]
    assert listed.serves("ilmm") and not listed.serves("conapo")
    assert _cfg(pipelines="*").serves("cualquiera")


def test_static_mode_requires_its_tokens():
    with pytest.raises(ValidationError, match="IIEGDB_STATIC_TOKENS"):
        _cfg(auth_mode="static", static_tokens=None)


def test_jwt_mode_requires_its_verification():
    with pytest.raises(ValidationError, match="IIEGDB_JWKS_URI, IIEGDB_ISSUER, IIEGDB_AUDIENCE"):
        _cfg(auth_mode="jwt")
    assert _cfg(auth_mode="jwt", jwks_uri="https://i/jwks", issuer="https://i/", audience="a")


def test_the_password_and_the_tokens_stay_out_of_the_repr():
    cfg = _cfg(pg_password="contrasena_real", static_tokens="token_real")
    text = f"{cfg!r} {cfg.pg_password} {cfg.static_tokens}"
    assert "contrasena_real" not in text and "token_real" not in text
