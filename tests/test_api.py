"""Las cinco rutas REST con TestClient. Sin base de datos y sin puerto.

El app se levanta de verdad —lifespan incluido— porque parte de lo que se prueba es el
montaje: que `/mcp` y `/v1` convivan en el mismo proceso y que la config se valide al
arrancar.
"""

import pytest

from indicadores_sieej import connections, engine
from indicadores_sieej.catalog import SUMMARY_FIELDS, get

from .conftest import ROW

INDICATOR = "incidencia_delictiva_municipal"
DATA = f"/v1/indicadores/{INDICATOR}/datos"


# --- Descubrimiento ---


def test_list_returns_the_reduced_view(api):
    response = api.get("/v1/indicadores")
    assert response.status_code == 200
    assert response.json() and all(tuple(row) == SUMMARY_FIELDS for row in response.json())


def test_list_filters_by_tema_and_by_nivel(api):
    by_tema = api.get("/v1/indicadores", params={"tema": "empleo"}).json()
    by_nivel = api.get("/v1/indicadores", params={"nivel": "estatal"}).json()
    assert by_tema and {row["tema"] for row in by_tema} == {"empleo"}
    assert by_nivel and {row["nivel"] for row in by_nivel} == {"estatal"}


def test_list_without_matches_is_an_empty_list_not_a_404(api):
    response = api.get("/v1/indicadores", params={"tema": "no_existe"})
    assert response.status_code == 200
    assert response.json() == []


def test_describe_returns_the_metadata_without_sql(api):
    response = api.get(f"/v1/indicadores/{INDICATOR}")
    assert response.status_code == 200
    assert response.json()["id"] == INDICATOR
    assert all(param["descripcion"] for param in response.json()["parametros"])
    assert "sql" not in response.json()


def test_describe_with_an_unknown_id_is_404(api):
    response = api.get("/v1/indicadores/no_existe")
    assert response.status_code == 404
    assert response.json()["detail"] == "Indicador 'no_existe' no existe en el catálogo"


# --- Datos: un código por fila de la tabla de errores ---


def test_data_returns_the_envelope(api, connection, process_settings):
    connection([ROW])
    response = api.get(DATA)
    assert response.status_code == 200
    envelope = response.json()
    assert envelope["indicador"] == INDICATOR
    assert envelope["parametros_aplicados"] == {"cve_geo": None, "tipo_delito": None, "anio_min": None}
    assert len(envelope["filas"]) == 1


def test_the_query_params_travel_with_the_name_the_yaml_declares(api, connection, process_settings):
    fake = connection([ROW])
    api.get(DATA, params={"cve_geo": "14039", "anio_min": "2020"})
    assert fake.binds["cve_geo"] == "14039"
    assert fake.binds["anio_min"] == 2020


def test_an_undeclared_query_param_is_400_not_ignored(api, connection, process_settings):
    """Ignorarlo en silencio le haría creer al cliente que su filtro se aplicó."""
    connection()
    response = api.get(DATA, params={"municipio": "14039"})
    assert response.status_code == 400
    assert response.json()["detail"] == f"{INDICATOR}: parámetros desconocidos ['municipio']"


def test_a_value_that_cannot_be_coerced_is_400(api, connection, process_settings):
    connection()
    response = api.get(DATA, params={"anio_min": "dos mil"})
    assert response.status_code == 400
    assert "no es un int válido" in response.json()["detail"]


def test_a_missing_required_param_is_400(api, connection, process_settings, monkeypatch):
    # Ninguno del piloto es requerido: se fuerza uno sobre un indicador real.
    required = get(INDICATOR).model_copy(deep=True)
    required.parametros[0].requerido = True
    monkeypatch.setattr(engine, "get", lambda _: required)
    connection()
    response = api.get(DATA)
    assert response.status_code == 400
    assert response.json()["detail"] == f"{INDICATOR}: falta el parámetro requerido 'cve_geo'"


def test_exceeding_the_limit_is_413_and_names_the_parameters(api, connection, process_settings):
    connection([ROW] * 5001)
    response = api.get(DATA)
    assert response.status_code == 413
    assert response.json()["detail"] == (
        f"{INDICATOR}: la consulta excede 5000 filas; acota con ['anio_min', 'cve_geo', 'tipo_delito']"
    )


def test_a_pipeline_without_dsn_is_503(api, connection, process_settings, monkeypatch):
    connection()
    monkeypatch.setattr(connections, "available", lambda *a, **k: False)
    response = api.get(DATA)
    assert response.status_code == 503
    assert response.json()["detail"] == f"{INDICATOR}: indicador no disponible en este despliegue"


def test_a_dead_database_is_502_and_leaks_nothing(api, connection, process_settings):
    connection(fails=True)
    response = api.get(DATA)
    assert response.status_code == 502
    assert "referencia:" in response.json()["detail"]


def test_data_of_an_unknown_indicator_is_404(api, connection, process_settings):
    connection()
    assert api.get("/v1/indicadores/no_existe/datos").status_code == 404


# --- Operación ---


def test_health_answers_without_authentication(api):
    """Es la única excepción; que siga siéndolo lo verifica la prueba de rutas de #18.

    `registro` sale `no_aplica` porque estas pruebas corren en modo `static`: el estado
    solo tiene sentido donde hay un registro que consultar.
    """
    response = api.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "registro": "no_aplica"}


def test_ready_reports_every_pipeline_without_opening_pools(api):
    response = api.get("/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["pipelines"]
    assert all(state["pool"] == "unopened" for state in payload["pipelines"].values())


def test_ready_is_503_when_no_pipeline_has_a_dsn(api, monkeypatch):
    monkeypatch.setattr(connections, "available", lambda *a, **k: False)
    response = api.get("/ready")
    assert response.status_code == 503
    assert response.json()["ready"] is False


@pytest.mark.parametrize("responds, expected", [(True, 200), (False, 503)])
def test_ready_for_one_pipeline_forces_the_check(api, monkeypatch, responds, expected):
    monkeypatch.setattr(connections, "check", lambda *a, **k: responds)
    response = api.get("/ready", params={"pipeline": "delitos"})
    assert response.status_code == expected
    assert response.json()["responds"] is responds


# --- Montaje ---


def test_the_openapi_describes_every_route(api):
    paths = api.get("/openapi.json").json()["paths"]
    assert set(paths) == {
        "/health",
        "/ready",
        "/v1/indicadores",
        "/v1/indicadores/{id}",
        "/v1/indicadores/{id}/datos",
        "/v1/api-keys",
        "/v1/api-keys/actual",
    }
    assert api.get("/docs").status_code == 200


def test_mcp_answers_in_the_same_process(api):
    """Si el lifespan del app MCP no se encadena, el gestor de sesiones no arranca y
    esto falla — sin ningún error al levantar, que es lo que lo hace traicionero."""
    response = api.post(
        "/mcp/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "t", "version": "1"},
            },
        },
        headers={"Accept": "application/json, text/event-stream", "Content-Type": "application/json"},
    )
    assert response.status_code == 200
    assert "protocolVersion" in response.text


def test_there_is_no_global_cors_middleware(api):
    """Un CORSMiddleware de nivel superior sobre el MCP rompe .well-known y OPTIONS."""
    names = [middleware.cls.__name__ for middleware in api.app.user_middleware]
    assert "CORSMiddleware" not in names
