"""Dobles compartidos por las pruebas del motor. Ninguna prueba abre una base."""

import pytest
from sqlalchemy.exc import OperationalError

from indicadores_sieej import config, connections, engine
from indicadores_sieej.catalog import COLUMNS
from indicadores_sieej.config import Settings

ROW = dict.fromkeys(COLUMNS, None)

# Lo mínimo que exige Settings. Se usa de dos formas: como kwargs para construirlas a
# mano, y como variables de entorno cuando la prueba levanta el app de verdad.
BASE = {
    "pg_host": "h",
    "pg_user": "u",
    "pg_password": "p",
    "pipelines": "*",
    "auth_mode": "static",
    "static_tokens": "t:c:indicadores:read",
    "base_url": "https://x",
}


def cfg(**overrides) -> Settings:
    """Settings completas sin leer el entorno ni el .env del desarrollador."""
    return Settings(_env_file=None, **{**BASE, **overrides})


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self._rows


class _Connection:
    """Registra lo que se ejecutó, para poder afirmar sobre ello."""

    def __init__(self, rows, fails=False):
        self.rows, self.fails = rows, fails
        self.query = self.binds = self.options = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execution_options(self, **options):
        self.options = options
        return self

    def execute(self, query, binds):
        self.query, self.binds = query, binds
        if self.fails:
            raise OperationalError("no importa", {}, Exception("base caída"))
        return _Result(self.rows)


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def connect(self):
        return self.connection


@pytest.fixture
def connection(monkeypatch):
    """Sustituye el pool real.

    Guardar la consulta ejecutada es lo que permite afirmar que los valores viajaron
    como binds y no dentro del texto del sql.
    """

    def _build(rows=(), fails=False):
        fake = _Connection(list(rows), fails)
        monkeypatch.setattr(connections, "pool", lambda *a, **k: _Pool(fake))
        monkeypatch.setattr(connections, "available", lambda *a, **k: True)
        return fake

    return _build


@pytest.fixture
def process_settings(monkeypatch):
    """Fija las settings del proceso sin leer el .env del desarrollador.

    Las superficies llaman al motor sin pasarle cfg — es el motor quien las resuelve —
    así que sustituirlas ahí es lo que las desconecta del entorno.
    """
    monkeypatch.setattr(engine, "settings", cfg)
    return cfg()


@pytest.fixture
def api(monkeypatch):
    """Cliente REST contra el app real, con su lifespan corrido y sin base de datos.

    Las settings se ponen en el entorno en vez de sustituirlas: así la prueba pasa por
    la validación de arranque, que es parte de lo que se está probando.
    """
    from fastapi.testclient import TestClient

    from indicadores_sieej.main import create_app

    for name, value in BASE.items():
        monkeypatch.setenv(f"IIEGDB_{name.upper()}", value)
    config.settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            yield client
    finally:
        config.settings.cache_clear()
