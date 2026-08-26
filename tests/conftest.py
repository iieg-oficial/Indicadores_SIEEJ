"""Dobles compartidos por las pruebas. Ninguna prueba abre una base ni un puerto."""

from contextlib import contextmanager

import pytest
from sqlalchemy.exc import OperationalError

from indicadores_sieej import auth, config, connections, engine
from indicadores_sieej.catalog import COLUMNS
from indicadores_sieej.config import Settings

ROW = dict.fromkeys(COLUMNS, None)

# Lo mínimo que exige Settings. Se usa de dos formas: como kwargs para construirlas a
# mano, y como variables de entorno cuando la prueba levanta el app de verdad.
# Dos tokens: uno con el scope del banco y otro válido pero sin él. Es lo que permite
# separar el 401 del 403 sin inventar un verificador de mentira.
TOKEN = "con_scope"
SCOPELESS = "sin_scope"

BASE = {
    "pg_host": "h",
    "pg_user": "u",
    "pg_password": "p",
    "pipelines": "*",
    "auth_mode": "static",
    "static_tokens": "con_scope:cliente_a:indicadores:read,sin_scope:cliente_b:otro:scope",
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


@contextmanager
def _client(monkeypatch, token):
    """Levanta el app real con su lifespan, sin base de datos.

    Las settings se ponen en el entorno en vez de sustituirlas: así la prueba pasa por
    la validación de arranque, que es parte de lo que se está probando.
    """
    from fastapi.testclient import TestClient

    from indicadores_sieej.main import create_app

    for name, value in BASE.items():
        monkeypatch.setenv(f"IIEGDB_{name.upper()}", value)
    config.settings.cache_clear()
    auth.verifier.cache_clear()
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with TestClient(create_app(), headers=headers) as client:
            yield client
    finally:
        config.settings.cache_clear()
        auth.verifier.cache_clear()


@pytest.fixture
def api(monkeypatch):
    """Cliente REST autenticado y con el scope del banco: el caso normal."""
    with _client(monkeypatch, TOKEN) as client:
        yield client


@pytest.fixture
def clients(monkeypatch):
    """Fábrica de clientes con el token que pida la prueba; None manda sin cabecera."""
    return lambda token: _client(monkeypatch, token)
