"""Garantía 1 del contrato: el campo `sql` nunca sale del servidor.

CA-4 exige que se verifique con una prueba, no con revisión manual. El barrido toma
el `sql` real de cada indicador del catálogo, así que sigue siendo válido cuando el
catálogo crezca: no hay ninguna lista de indicadores escrita a mano.

Cuando cierren las superficies (#13, #14) hay que extenderlo a las respuestas MCP y REST.
"""

import json
import logging

import pytest
import yaml

from indicadores_sieej import connections, engine
from indicadores_sieej.catalog import CATALOG_DIR, find, get, load
from indicadores_sieej.errors import InvalidCatalog, BankError

from .conftest import FILA, cfg as _cfg

INDICADORES = list(load().values())

# Fragmentos que solo pueden venir del sql. El nombre de la vista queda fuera a
# propósito: viaja legítimamente en el campo `origen` de la metadata.
FRAGMENTOS = sorted(
    {
        linea.strip()
        for ind in INDICADORES
        for linea in ind.sql.splitlines()
        if len(linea.strip()) >= 25 and linea.strip() != ind.origen
    }
)


def _sin_sql(texto: str, contexto: str) -> None:
    for ind in INDICADORES:
        assert ind.sql not in texto, f"{contexto}: se filtró el sql de {ind.id}"
    for fragmento in FRAGMENTOS:
        assert fragmento not in texto, f"{contexto}: se filtró un fragmento de sql — {fragmento!r}"


def test_hay_fragmentos_que_barrer():
    # Si el catálogo cambiara de forma y esto quedara vacío, el resto pasaría en falso.
    assert len(FRAGMENTOS) > 20


def test_listar_no_lleva_sql():
    _sin_sql(json.dumps(find(), ensure_ascii=False, default=str), "listar")


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_la_metadata_no_lleva_sql(ind):
    _sin_sql(json.dumps(ind.metadata(), ensure_ascii=False, default=str), f"metadata de {ind.id}")


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_el_sobre_de_respuesta_no_lleva_sql(ind, conexion):
    conexion([FILA])
    sobre = engine.execute(ind.id, cfg=_cfg())
    _sin_sql(json.dumps(sobre, ensure_ascii=False, default=str), f"sobre de {ind.id}")


def test_la_prueba_detecta_una_regresion():
    """Canario: si alguien devolviera el modelo completo en vez de metadata(), esto
    tiene que fallar. Sin esta prueba, las de arriba podrían pasar en falso."""
    completo = json.dumps(INDICADORES[0].model_dump(), ensure_ascii=False, default=str)
    with pytest.raises(AssertionError):
        _sin_sql(completo, "canario")


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_los_errores_del_motor_no_llevan_sql(ind, conexion, monkeypatch):
    mensajes = []

    conexion([FILA] * 5001)
    for llamada in (
        lambda: engine.execute(ind.id, cfg=_cfg(), parametro_inventado="x"),
        lambda: engine.execute(ind.id, cfg=_cfg()),  # excede el límite
    ):
        with pytest.raises(BankError) as exc:
            llamada()
        mensajes.append(str(exc.value))

    conexion(falla=True)
    with pytest.raises(BankError) as exc:
        engine.execute(ind.id, cfg=_cfg())
    mensajes.append(str(exc.value))

    monkeypatch.setattr(connections, "available", lambda *a, **k: False)
    with pytest.raises(BankError) as exc:
        engine.execute(ind.id, cfg=_cfg())
    mensajes.append(str(exc.value))

    _sin_sql("\n".join(mensajes), f"errores de {ind.id}")


@pytest.mark.parametrize("ind", INDICADORES, ids=lambda i: i.id)
def test_los_errores_del_catalogo_no_llevan_sql(ind, tmp_path):
    """La validación del sql es el lugar más fácil por donde se escaparía: tiene el
    sql en la mano cuando redacta el mensaje."""
    datos = yaml.safe_load((CATALOG_DIR / ind.tema / f"{ind.id}.yaml").read_text(encoding="utf-8"))
    datos["sql"] = ind.sql.replace("AS cve_geo", "AS clave")
    carpeta = tmp_path / ind.tema
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"{ind.id}.yaml").write_text(yaml.safe_dump(datos, allow_unicode=True), encoding="utf-8")

    with pytest.raises(InvalidCatalog) as exc:
        load(tmp_path)
    _sin_sql(str(exc.value), f"catálogo inválido de {ind.id}")


def test_los_logs_no_llevan_sql(conexion, caplog):
    """Ni en INFO ni en ERROR: el registro de una consulta fallida es donde se cuela
    el sql si se registra la excepción de SQLAlchemy completa."""
    ind = INDICADORES[0]

    with caplog.at_level(logging.INFO):
        conexion([FILA])
        engine.execute(ind.id, cfg=_cfg())

        conexion(falla=True)
        with pytest.raises(BankError):
            engine.execute(ind.id, cfg=_cfg())

    _sin_sql(caplog.text, "logs INFO+")


def test_obtener_expone_el_sql_solo_puertas_adentro():
    # El motor sí necesita el sql: la garantía es que no salga, no que no exista.
    assert get(INDICADORES[0].id).sql
