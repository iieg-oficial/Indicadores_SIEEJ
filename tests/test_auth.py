"""Autenticación y autorización, en **las dos superficies**.

Probar solo REST no bastaría: la garantía de docs/garantias.md es que MCP y REST
comparten la verificación, y eso solo se demuestra ejercitando las dos con los mismos
casos y comprobando que pasan por la misma función.
"""

import pytest
from fastapi.routing import APIRoute
from starlette.routing import Mount

from indicadores_sieej import auth, config

from .conftest import SCOPELESS, TOKEN

MCP_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _mcp(client):
    return client.post("/mcp/", json=MCP_BODY, headers=MCP_HEADERS)


def _rest(client):
    return client.get("/v1/indicadores")


def _api_routes(container):
    """Todas las rutas GET del app, recursivo.

    FastAPI no aplana los routers incluidos: `app.routes` trae contenedores, no rutas,
    y quedarse en el primer nivel haría que el recorrido de abajo pasara sin mirar nada.
    """
    for route in getattr(container, "routes", []):
        if isinstance(route, Mount):
            continue
        if isinstance(route, APIRoute):
            if "GET" in route.methods:
                yield route
        else:
            yield from _api_routes(getattr(route, "original_router", route))


# --- Los cinco casos, repetidos contra las dos superficies ---


@pytest.mark.parametrize("surface", [_mcp, _rest], ids=["mcp", "rest"])
@pytest.mark.parametrize(
    "token, expected",
    [
        (None, 401),
        ("no_existe", 401),
        ("Bearer sin el token", 401),
        (SCOPELESS, 403),
        (TOKEN, 200),
    ],
    ids=["sin cabecera", "token inexistente", "cabecera mal formada", "sin el scope", "con el scope"],
)
def test_both_surfaces_answer_the_same_to_the_same_token(clients, surface, token, expected):
    with clients(token) as client:
        assert surface(client).status_code == expected


def test_health_is_the_only_route_without_authentication(clients):
    with clients(None) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- La regresión que importa el día que alguien agregue una ruta ---


def test_every_registered_route_but_health_demands_authentication(clients):
    """Una ruta nueva nace protegida porque la dependencia va en el router. Esto es lo
    que se entera si alguien la registra por fuera."""
    with clients(None) as client:
        unprotected = []
        # La sub-app MCP no es una ruta: se sondea por su propio endpoint.
        if _mcp(client).status_code != 401:
            unprotected.append("/mcp")
        for route in _api_routes(client.app):
            path = route.path.format(id="cualquiera")
            if path == "/health":
                continue
            if client.get(path).status_code != 401:
                unprotected.append(path)

    assert unprotected == [], f"responden sin token: {unprotected}"


def test_the_sweep_covers_every_route(clients):
    """Canario: si el recorrido dejara de ver rutas, la prueba de arriba pasaría vacía."""
    with clients(None) as client:
        paths = {route.path for route in _api_routes(client.app)}
    assert paths == {
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
        "/v1/indicadores",
        "/v1/indicadores/{id}",
        "/v1/indicadores/{id}/datos",
    }


# --- Una sola verificación para las dos superficies ---


def test_both_surfaces_resolve_the_identity_with_the_same_function(clients, monkeypatch):
    """SEG-9: no dos implementaciones de auth en el mismo proceso, una."""
    calls = []
    original = auth.identify

    async def spy(authorization):
        calls.append(authorization)
        return await original(authorization)

    monkeypatch.setattr(auth, "identify", spy)

    with clients(TOKEN) as client:
        assert _rest(client).status_code == 200
        assert _mcp(client).status_code == 200

    assert calls == [f"Bearer {TOKEN}"] * 2


# --- Lo que no se filtra ---


def test_the_messages_do_not_say_which_token_failed(clients):
    """Quien prueba tokens no debe aprender nada del texto más allá del código."""
    with clients("no_existe") as client:
        invalid = client.get("/v1/indicadores").json()["detail"]
    with clients(None) as client:
        absent = client.get("/v1/indicadores").json()["detail"]
    with clients(SCOPELESS) as client:
        scopeless = client.get("/v1/indicadores").json()["detail"]

    assert absent == "no autenticado"
    assert invalid == "token inválido"
    assert scopeless == "el token no tiene el scope 'indicadores:read'"


@pytest.mark.parametrize("token", [TOKEN, SCOPELESS, "no_existe"])
def test_no_token_reaches_the_logs_or_the_response(clients, caplog, token):
    import logging

    with caplog.at_level(logging.DEBUG):
        with clients(token) as client:
            body = client.get("/v1/indicadores").text
    assert token not in caplog.text
    assert token not in body


def test_a_token_is_revoked_by_removing_it_from_the_variable(clients, monkeypatch):
    """SEG-12: revocar es quitar la entrada y reiniciar; no hay estado que limpiar."""
    with clients(TOKEN) as client:
        assert client.get("/v1/indicadores").status_code == 200

        # Revocar es quitar la entrada de la variable y reiniciar el proceso; aquí se
        # simula el reinicio soltando las dos cachés que lo hacen barato en producción.
        monkeypatch.setenv("IIEGDB_STATIC_TOKENS", f"{SCOPELESS}:cliente_b:otro:scope")
        config.settings.cache_clear()
        auth.verifier.cache_clear()

        assert client.get("/v1/indicadores").status_code == 401


# --- El parseo de IIEGDB_STATIC_TOKENS ---


def test_the_static_tokens_parse_client_and_scopes():
    parsed = auth._static_tokens("a:cliente_a:indicadores:read otro:scope, b:cliente_b:indicadores:read")
    assert parsed["a"] == {"client_id": "cliente_a", "scopes": ["indicadores:read", "otro:scope"]}
    assert parsed["b"]["client_id"] == "cliente_b"


def test_a_malformed_entry_fails_without_printing_the_token():
    with pytest.raises(ValueError) as exc:
        auth._static_tokens("token_secreto:sin_scope")
    assert "token_secreto" not in str(exc.value)
