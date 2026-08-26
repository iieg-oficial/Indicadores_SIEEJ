"""Dobles compartidos por las pruebas del motor. Ninguna prueba abre una base."""

import pytest
from sqlalchemy.exc import OperationalError

from indicadores_sieej import conexiones
from indicadores_sieej.catalogo import COLUMNAS
from indicadores_sieej.config import Settings

FILA = dict.fromkeys(COLUMNAS, None)


def cfg(**cambios) -> Settings:
    """Settings completas sin leer el entorno ni el .env del desarrollador."""
    base = {
        "pg_host": "h",
        "pg_user": "u",
        "pg_password": "p",
        "pipelines": "*",
        "auth_mode": "static",
        "static_tokens": "t:c:indicadores:read",
        "base_url": "https://x",
    }
    return Settings(_env_file=None, **{**base, **cambios})


class _Resultado:
    def __init__(self, filas):
        self._filas = filas

    def mappings(self):
        return self._filas


class _Conexion:
    """Registra lo que se ejecutó, para poder afirmar sobre ello."""

    def __init__(self, filas, falla=False):
        self.filas, self.falla = filas, falla
        self.consulta = self.binds = self.opciones = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execution_options(self, **opciones):
        self.opciones = opciones
        return self

    def execute(self, consulta, binds):
        self.consulta, self.binds = consulta, binds
        if self.falla:
            raise OperationalError("no importa", {}, Exception("base caída"))
        return _Resultado(self.filas)


class _Pool:
    def __init__(self, conexion):
        self.conexion = conexion

    def connect(self):
        return self.conexion


@pytest.fixture
def conexion(monkeypatch):
    """Sustituye el pool real.

    Guardar la consulta ejecutada es lo que permite afirmar que los valores viajaron
    como binds y no dentro del texto del sql.
    """

    def _montar(filas=(), falla=False):
        falsa = _Conexion(list(filas), falla)
        monkeypatch.setattr(conexiones, "pool", lambda *a, **k: _Pool(falsa))
        monkeypatch.setattr(conexiones, "disponible", lambda *a, **k: True)
        return falsa

    return _montar
