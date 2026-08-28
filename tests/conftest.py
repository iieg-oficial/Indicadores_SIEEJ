"""Dobles compartidos por las pruebas. Ninguna prueba abre una base ni un puerto."""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError

from indicadores_sieej import auth, config, connections, engine, limits, registry
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


# --- El registro de API keys, sin PostgreSQL -----------------------------------------

API_KEY_MODE = {
    "auth_mode": "api_key",
    "registry_dsn": "postgresql://registro:x@localhost:5432/registro",
}

# Un origen fijo para las marcas de tiempo del doble. La fecha no significa nada; lo que
# importa es que sea la misma en cada corrida.
ORIGIN = datetime(2026, 1, 1, tzinfo=timezone.utc)

# Los singletons del proceso, capturados antes de que ninguna prueba los sustituya.
CACHED = (config.settings, auth.verifier, limits.issue_limiter)


class Clock:
    """Reloj falso, compartido por el doble y por el verificador.

    Es lo que convierte «cien días de uso» en un bucle en vez de en una espera, y lo que
    permite parar la caducidad justo en el borde en vez de cerca de él.
    """

    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> "Clock":
        self.now += seconds
        return self


class InMemoryApiKeyStore:
    """El registro con la misma semántica y sin base de datos.

    Lo que un doble no puede demostrar —que la migración se aplica, que el índice parcial
    cierra la carrera de emisión— vive en test_registry_db.py, marcado `integration`.
    Todo lo demás se prueba aquí, y por eso corre en CI.

    `finds` y `touches` cuentan **viajes al registro**, no escrituras efectivas: es la
    carga real, que es lo que el refresco acotado existe para bajar.
    """

    def __init__(self, clock: Clock, ttl_days: int = 90):
        self.clock = clock
        self.ttl_s = ttl_days * 86400
        self.rows: dict[UUID, dict] = {}
        self.by_hash: dict[str, UUID] = {}
        self.down = False
        self.finds = self.touches = 0

    def find(self, key_hash: str):
        self._responds()
        self.finds += 1
        row = self.rows.get(self.by_hash.get(key_hash))
        if row is None or row["revoked_at"] is not None:
            return None
        idle = self.clock() - row["last_used_at"]
        # Caducada por desuso: indistinguible de inexistente, a propósito.
        return None if idle > self.ttl_s else self._stored(row, idle)

    def touch(self, id: UUID, throttle_s: int) -> None:
        self._responds()
        self.touches += 1
        row = self.rows[id]
        if self.clock() - row["last_used_at"] >= throttle_s:
            row["last_used_at"] = self.clock()

    def issue(self, correo: str):
        self._responds()
        key, key_hash, prefijo = registry.new_key()
        for row in self.rows.values():
            if row["correo"] == correo and row["revoked_at"] is None:
                row["revoked_at"] = self.clock()
        id = uuid4()
        self.rows[id] = {
            "id": id,
            "correo": correo,
            "prefijo": prefijo,
            "scopes": [auth.SCOPE],
            "created_at": self.clock(),
            "last_used_at": self.clock(),
            "revoked_at": None,
        }
        self.by_hash[key_hash] = id
        return key, self._stored(self.rows[id], 0)

    def revoke(self, id: UUID) -> None:
        self._responds()
        self.rows[id]["revoked_at"] = self.clock()

    def _responds(self) -> None:
        """Cae **por el mismo traductor** que la implementación de PostgreSQL.

        Levantar `RegistryUnavailable` a mano ahorraría dos líneas y dejaría sin probar
        justo lo que se quiere probar: la traducción a 503 y el estado que `/health`
        reporta viven ahí, no aquí.
        """
        with registry.unavailable_on_failure():
            if self.down:
                raise OperationalError("el registro no responde", {}, Exception("registro caído"))

    def _stored(self, row: dict, idle: float) -> registry.StoredKey:
        return registry.StoredKey(
            id=row["id"],
            correo=row["correo"],
            prefijo=row["prefijo"],
            scopes=list(row["scopes"]),
            created_at=ORIGIN + timedelta(seconds=row["created_at"]),
            last_used_at=ORIGIN + timedelta(seconds=row["last_used_at"]),
            expires_at=int(row["last_used_at"] + self.ttl_s),
            idle_s=int(idle),
        )


@dataclass
class ApiKeyHarness:
    """El registro en memoria, su reloj y un app en modo `api_key` sobre los dos."""

    store: InMemoryApiKeyStore
    clock: Clock
    _monkeypatch: pytest.MonkeyPatch

    def settings(self, **overrides) -> Settings:
        return cfg(**{**API_KEY_MODE, **overrides})

    def verifier(self, **overrides) -> "auth.ApiKeyVerifier":
        """El verificador suelto, sin levantar el app. Para las pruebas de reloj largo."""
        return auth.ApiKeyVerifier(self.store, self.settings(**overrides), clock=self.clock)

    @contextmanager
    def client(self, **overrides):
        """El app real en modo `api_key`, con el doble detrás de las dos superficies."""
        from fastapi.testclient import TestClient

        from indicadores_sieej.main import create_app

        for name, value in {**BASE, **API_KEY_MODE, **overrides}.items():
            self._monkeypatch.setenv(f"IIEGDB_{name.upper()}", str(value))
        self._reset()

        verifier = self.verifier(**overrides)
        limiter = limits.IssueLimiter(self.settings(**overrides), clock=self.clock)
        # Se sustituye la fábrica y no `verifier()`: así el caché del proceso y su
        # limpieza siguen siendo los de producción. El limitador lleva el mismo reloj
        # falso, que es lo que permite adelantar una hora sin esperarla.
        self._monkeypatch.setattr(auth, "build_verifier", lambda _cfg: verifier)
        self._monkeypatch.setattr(limits, "issue_limiter", lambda: limiter)
        try:
            with TestClient(create_app()) as client:
                yield client
        finally:
            self._reset()

    @staticmethod
    def _reset() -> None:
        """Suelta los singletons del proceso. El limitador cuenta por proceso, así que sin
        soltarlo una prueba se llevaría las emisiones de la anterior.

        Se limpian por la referencia de CACHED y no por el nombre del módulo, que para
        entonces puede estar sustituido por el doble de esta misma clase.
        """
        for cached in CACHED:
            cached.cache_clear()
        registry.close()


@pytest.fixture
def api_keys(monkeypatch) -> ApiKeyHarness:
    clock = Clock()
    return ApiKeyHarness(InMemoryApiKeyStore(clock), clock, monkeypatch)
