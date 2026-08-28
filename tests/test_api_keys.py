"""El verificador de API keys, en las dos superficies y sin base de datos.

Todo lo de aquí corre en CI. El doble en memoria de conftest.py tiene la misma semántica
que el registro real —revocación, caducidad por desuso, refresco acotado, caída— y
comparte reloj con el verificador, que es lo que permite simular cien días en un bucle.

Lo que un doble no puede demostrar vive en test_registry_db.py, marcado `integration`.
"""

import logging
from dataclasses import replace
from uuid import UUID

import pytest

from indicadores_sieej import auth, limits, registry
from indicadores_sieej.errors import RateLimited, RegistryUnavailable

from .conftest import API_KEY_MODE, TOKEN, cfg

CORREO = "alguien@iieg.mx"


@pytest.fixture(autouse=True)
def _clean_registry_state():
    """`_STATE` es global: sin esto, una prueba se lleva el estado observado de la anterior."""
    registry.close()
    yield
    registry.close()


MCP_BODY = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}},
}
MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def _mcp(client, key):
    headers = {**MCP_HEADERS, "Authorization": f"Bearer {key}"}
    return client.post("/mcp/", json=MCP_BODY, headers=headers)


def _rest(client, key):
    return client.get("/v1/indicadores", headers={"Authorization": f"Bearer {key}"})


# --- El modo de producción se enchufa ---


def test_the_api_key_mode_builds_the_registry_verifier():
    """Sin esta rama, `IIEGDB_AUTH_MODE=api_key` arrancaba y caía al verificador
    estático: la configuración decía una cosa y el proceso hacía otra."""
    assert isinstance(auth.build_verifier(cfg(**API_KEY_MODE)), auth.ApiKeyVerifier)


def test_building_the_verifier_opens_no_connection():
    """Un DSN malo se entera en la primera verificación, con un 503, no tumbando el
    arranque de un servidor que todavía podía servir /health."""
    verifier = auth.build_verifier(cfg(**API_KEY_MODE))
    assert isinstance(verifier.store, registry.PostgresApiKeyStore)
    assert registry._ENGINE is None


# --- Los mismos casos contra las dos superficies ---


@pytest.mark.parametrize("surface", [_mcp, _rest], ids=["mcp", "rest"])
def test_a_registry_key_authenticates_on_both_surfaces(api_keys, surface):
    key, _ = api_keys.store.issue(CORREO)
    with api_keys.client() as client:
        assert surface(client, key).status_code == 200


@pytest.mark.parametrize("surface", [_mcp, _rest], ids=["mcp", "rest"])
def test_a_revoked_key_is_401_on_both_surfaces(api_keys, surface):
    key, stored = api_keys.store.issue(CORREO)
    api_keys.store.revoke(stored.id)
    with api_keys.client() as client:
        assert surface(client, key).status_code == 401


@pytest.mark.parametrize("surface", [_mcp, _rest], ids=["mcp", "rest"])
def test_a_key_expired_by_disuse_is_401_on_both_surfaces(api_keys, surface):
    key, _ = api_keys.store.issue(CORREO)
    api_keys.clock.advance(91 * 86400)
    with api_keys.client() as client:
        assert surface(client, key).status_code == 401


def test_an_unknown_key_is_401(api_keys):
    with api_keys.client() as client:
        assert _rest(client, "iieg_no_existe").status_code == 401


# --- La caducidad se mide por desuso, no por antigüedad ---


async def test_the_ninety_day_window_closes_on_the_day(api_keys):
    """Justo dentro pasa y justo fuera no. Probar solo «muy vieja» dejaría sin cubrir el
    borde, que es donde vive el error de un signo.

    Van dos keys y no una porque verificar **refresca**: reusar la primera mediría el
    refresco en vez de la ventana, y pasaría siempre.
    """
    dentro, _ = api_keys.store.issue("dentro@iieg.mx")
    fuera, _ = api_keys.store.issue("fuera@iieg.mx")
    verifier = api_keys.verifier()

    api_keys.clock.advance(90 * 86400)
    assert await verifier.verify_token(dentro) is not None

    api_keys.clock.advance(2)
    assert await verifier.verify_token(fuera) is None


async def test_a_key_used_every_thirty_seconds_survives_a_hundred_days(api_keys):
    """El criterio que da sentido a todo el mecanismo: una key **en uso** no caduca
    nunca, aunque la ventana de desuso sea de noventa días.

    El caché va en diez minutos y no en el minuto de producción por una razón de la
    prueba y no del diseño: con 288 000 usos simulados, cada fallo de caché es un viaje
    al registro, y el minuto convertiría un segundo de CI en varios. Lo que se ejercita
    es idéntico — orden de ventanas, refresco acotado y desalojo — y el orden que
    config.py exige se sigue cumpliendo.
    """
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier(api_key_cache_ttl_s=600)

    usos = 100 * 86400 // 30
    for _ in range(usos):
        api_keys.clock.advance(30)
        assert await verifier.verify_token(key) is not None

    # El refresco es acotado: doscientos ochenta y ocho mil usos, un refresco por hora.
    assert api_keys.store.touches <= 100 * 24 + 1
    assert api_keys.store.finds < usos // 10


# --- El refresco del último uso ---


async def test_the_last_use_is_not_written_once_per_request(api_keys):
    """Sin el acotado, cada petición sería un UPDATE contra la misma fila: el registro
    se convertiría en el cuello de botella de todo el servidor."""
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    for _ in range(100):
        api_keys.clock.advance(1)
        await verifier.verify_token(key)

    assert api_keys.store.touches == 0


async def test_the_refresh_is_driven_by_real_use_and_not_by_the_cache_miss(api_keys):
    """Pasada la ventana de refresco, el siguiente uso la refresca. Una sola vez: el
    uso inmediatamente siguiente ya no vuelve a escribir."""
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    api_keys.clock.advance(3601)
    await verifier.verify_token(key)
    assert api_keys.store.touches == 1

    api_keys.clock.advance(1)
    await verifier.verify_token(key)
    assert api_keys.store.touches == 1


async def test_a_key_seen_after_a_long_idle_is_refreshed_at_once(api_keys):
    """El almacén devuelve cuánto llevaba parada la key —`idle_s`— justamente para esto.
    Sin ese dato, una key que vuelve tras semanas esperaría una hora más antes de
    refrescarse, y con reinicios del proceso podría no refrescarse nunca."""
    key, _ = api_keys.store.issue(CORREO)
    api_keys.clock.advance(30 * 86400)

    await api_keys.verifier().verify_token(key)
    assert api_keys.store.touches == 1


async def test_a_failed_refresh_never_brings_down_an_authentication(api_keys, caplog):
    """Refrescar el último uso es contabilidad, no autorización. Si tumbara la
    verificación, un registro lento dejaría fuera a quien tiene una credencial válida."""
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()
    api_keys.clock.advance(3601)

    def _falla(*_args):
        raise RegistryUnavailable("el registro de API keys no está disponible")

    api_keys.store.touch = _falla
    with caplog.at_level(logging.WARNING):
        assert await verifier.verify_token(key) is not None
    assert "refrescar" in caplog.text


# --- El caché ---


async def test_the_second_use_does_not_query_the_registry(api_keys):
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    await verifier.verify_token(key)
    await verifier.verify_token(key)
    assert api_keys.store.finds == 1


async def test_the_cache_entry_never_outlives_the_key(api_keys):
    """Las tres ventanas de la entrada se acotan contra la caducidad de la propia key.
    Con eso, la corrección deja de depender del orden de las ventanas configuradas — que
    config.py valida igual al arrancar."""
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier(api_key_cache_ttl_s=600)

    # A diez segundos de caducar: ni el caché de diez minutos ni la ventana rancia caben
    # enteros sin que la entrada le sobreviva.
    stored = api_keys.store.find(registry.hashed(key))
    entry = verifier._remember("h", replace(stored, idle_s=90 * 86400 - 10), now=0.0)

    assert entry.dead_at == entry.fresh_until == entry.stale_until == 10


async def test_a_failed_verification_is_never_cached(api_keys):
    """Cachear el negativo dejaría que un anónimo llene la memoria con hashes
    inventados: el tamaño quedaría atado a lo que manda el atacante."""
    verifier = api_keys.verifier()
    for i in range(50):
        await verifier.verify_token(f"iieg_inventada_{i}")
    assert verifier._cache == {}


async def test_forgetting_a_key_makes_its_revocation_immediate_in_this_process(api_keys):
    key, stored = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    access = await verifier.verify_token(key)
    api_keys.store.revoke(stored.id)
    assert await verifier.verify_token(key) is not None  # todavía en caché

    verifier.forget(access.token)
    assert await verifier.verify_token(key) is None


# --- El registro caído es 503, nunca 401 ---


@pytest.mark.parametrize("surface", [_mcp, _rest], ids=["mcp", "rest"])
def test_a_dead_registry_is_503_on_both_surfaces(api_keys, surface):
    """Un 401 le diría a cada consumidor que su credencial es mala y los mandaría a
    todos a pedir una nueva: un parpadeo del registro se volvería una estampida."""
    key, _ = api_keys.store.issue(CORREO)
    api_keys.store.down = True
    with api_keys.client() as client:
        assert surface(client, key).status_code == 503


def test_health_stays_200_with_the_registry_down_and_says_so(api_keys):
    """`/ready` exige credencial, así que con el registro caído devuelve 503 antes del
    handler: sin esto el operador no distingue «registro caído» de «todo caído».

    Y `/health` sigue en 200 a propósito: es liveness de *este* proceso, y un 503 haría
    que el orquestador reinicie un servidor sano porque el registro parpadeó.
    """
    key, _ = api_keys.store.issue(CORREO)
    with api_keys.client() as client:
        assert client.get("/health").json() == {"status": "ok", "registro": "desconocido"}

        api_keys.store.down = True
        assert _rest(client, key).status_code == 503
        health = client.get("/health")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "registro": "caido"}


def test_health_reports_the_registry_as_ok_after_a_real_verification(api_keys):
    key, _ = api_keys.store.issue(CORREO)
    with api_keys.client() as client:
        assert _rest(client, key).status_code == 200
        assert client.get("/health").json()["registro"] == "ok"


def test_health_never_opens_a_connection_to_report(api_keys):
    """Es la única ruta anónima del servidor: sondear la base desde ella la convertiría
    en un amplificador de DoS."""
    with api_keys.client() as client:
        assert client.get("/health").json()["registro"] == "desconocido"
    assert api_keys.store.finds == 0


# --- El caché rancio durante una caída ---


async def test_a_stale_entry_is_served_while_the_registry_is_down(api_keys):
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    await verifier.verify_token(key)
    api_keys.store.down = True
    api_keys.clock.advance(61)  # fuera del caché fresco, dentro del rancio

    assert await verifier.verify_token(key) is not None


async def test_past_the_stale_window_a_dead_registry_is_503_again(api_keys):
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    await verifier.verify_token(key)
    api_keys.store.down = True
    api_keys.clock.advance(601)

    with pytest.raises(RegistryUnavailable):
        await verifier.verify_token(key)


async def test_a_key_already_known_dead_is_not_resurrected_by_an_outage(api_keys):
    """El caché solo guarda positivos, y el negativo desaloja. Si no, una caída
    posterior devolvería a la vida a una key ya revocada."""
    key, stored = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    await verifier.verify_token(key)
    api_keys.store.revoke(stored.id)
    api_keys.clock.advance(61)
    assert await verifier.verify_token(key) is None

    api_keys.store.down = True
    with pytest.raises(RegistryUnavailable):
        await verifier.verify_token(key)


async def test_the_stale_window_never_outlives_the_key_itself(api_keys):
    """Aguantar una caída no puede convertirse en resucitar una caducada."""
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier()

    api_keys.clock.advance(90 * 86400 - 5)
    await verifier.verify_token(key)
    api_keys.store.down = True
    api_keys.clock.advance(10)

    with pytest.raises(RegistryUnavailable):
        await verifier.verify_token(key)


async def test_the_stale_window_can_be_turned_off(api_keys):
    """La salida para un despliegue que prefiera cortar antes que aguantar."""
    key, _ = api_keys.store.issue(CORREO)
    verifier = api_keys.verifier(api_key_stale_s=0)

    await verifier.verify_token(key)
    api_keys.store.down = True
    api_keys.clock.advance(61)

    with pytest.raises(RegistryUnavailable):
        await verifier.verify_token(key)


def test_a_stale_window_shorter_than_the_cache_does_not_start(api_keys):
    """Sería código muerto disfrazado de configuración: la entrada dejaría de ser
    servible antes de volverse rancia."""
    with pytest.raises(ValueError, match="IIEGDB_API_KEY_STALE_S"):
        cfg(**API_KEY_MODE, api_key_cache_ttl_s=60, api_key_stale_s=30)


# --- La identidad que sale, y lo que no sale ---


async def test_the_identity_is_the_uuid_and_never_the_email(api_keys):
    """Si el correo viajara como identidad, cada línea del log de auditoría de #21
    sería dato personal."""
    key, stored = api_keys.store.issue(CORREO)
    access = await api_keys.verifier().verify_token(key)

    assert access.client_id == access.subject == str(stored.id)
    assert UUID(access.client_id) == stored.id
    assert CORREO not in (access.client_id, access.subject, access.token)


async def test_the_access_token_carries_the_hash_and_never_the_key(api_keys):
    """El campo es obligatorio en el modelo de FastMCP y el objeto acaba en manos de
    terceros; con el hash ahí, la key en claro no existe más allá de quien la convirtió."""
    key, _ = api_keys.store.issue(CORREO)
    access = await api_keys.verifier().verify_token(key)

    assert access.token == registry.hashed(key)
    assert key not in access.model_dump_json()


async def test_the_claims_carry_what_the_self_service_route_needs(api_keys):
    """`GET /v1/api-keys/actual` sale de aquí sin volver a tocar la base."""
    key, stored = api_keys.store.issue(CORREO)
    access = await api_keys.verifier().verify_token(key)

    assert access.claims["correo"] == CORREO
    assert access.claims["prefijo"] == stored.prefijo
    assert access.expires_at == stored.expires_at
    assert access.scopes == [auth.SCOPE]


def test_the_key_in_the_clear_is_never_stored(api_keys):
    key, _ = api_keys.store.issue(CORREO)
    row = next(iter(api_keys.store.rows.values()))

    assert key not in str(row)
    assert registry.hashed(key) in api_keys.store.by_hash
    assert row["prefijo"] == key[: registry.PREFIX_LEN]


@pytest.mark.parametrize("surface", [_mcp, _rest], ids=["mcp", "rest"])
def test_neither_the_key_nor_the_email_reach_the_logs(api_keys, caplog, surface):
    """El correo también es dato personal: no basta con cuidar la credencial."""
    key, _ = api_keys.store.issue(CORREO)
    with caplog.at_level(logging.DEBUG):
        with api_keys.client() as client:
            body = surface(client, key).text

    assert key not in caplog.text and key not in body
    assert CORREO not in caplog.text and CORREO not in body


# --- La emisión: la única ruta pública de escritura ---


def _issue(client, correo=CORREO, **body):
    return client.post("/v1/api-keys", json={"correo": correo, **body})


def test_an_issued_key_works_at_once_on_both_surfaces(api_keys):
    """El criterio que da sentido a la ruta: quien pide una key la puede usar sin ningún
    paso intermedio, en las dos superficies."""
    with api_keys.client() as client:
        emitida = _issue(client)
        assert emitida.status_code == 201
        key = emitida.json()["api_key"]

        assert _rest(client, key).status_code == 200
        assert _mcp(client, key).status_code == 200


def test_the_issued_body_carries_the_key_the_email_and_the_expiry(api_keys):
    with api_keys.client() as client:
        body = _issue(client).json()

    assert body["api_key"].startswith(registry.PREFIX)
    assert body["correo"] == CORREO
    assert body["expira_en"].endswith("Z")
    assert set(body) == {"api_key", "correo", "expira_en"}


def test_the_key_is_never_cached_by_anything_in_the_middle(api_keys):
    with api_keys.client() as client:
        assert _issue(client).headers["cache-control"] == "no-store"


def test_issuing_needs_no_credential(api_keys):
    """Es la segunda ruta abierta del servidor, y tiene que serlo: exigir una credencial
    para obtener la primera sería un círculo. Su excepción está declarada en OPEN_ROUTES."""
    with api_keys.client() as client:
        assert client.post("/v1/api-keys", json={"correo": CORREO}).status_code == 201


def test_the_email_is_normalized_before_being_stored(api_keys):
    with api_keys.client() as client:
        assert _issue(client, correo="  Alguien@IIEG.MX  ").json()["correo"] == CORREO
    assert [row["correo"] for row in api_keys.store.rows.values()] == [CORREO]


@pytest.mark.parametrize("correo", ["no-es-correo", "", "a@", "@iieg.mx"])
def test_a_malformed_email_is_400_and_never_echoes_it(api_keys, correo):
    """400 y no el 422 de fábrica: docs/errores.md ya asigna el 400 a los parámetros
    inválidos, y el detalle de pydantic repetiría el correo en la respuesta."""
    with api_keys.client() as client:
        response = _issue(client, correo=correo)

    assert response.status_code == 400
    assert response.json()["detail"] == "petición inválida: ['correo']"
    assert correo not in response.text or not correo


def test_scopes_in_the_body_are_rejected(api_keys):
    """Un `scopes` en el cuerpo de una petición pública sin autenticar es escalada de
    privilegios. Los pone el servidor, y esta ruta no los acepta de fuera."""
    with api_keys.client() as client:
        response = _issue(client, scopes=["admin"])
        assert response.status_code == 400
        assert response.json()["detail"] == "petición inválida: ['scopes']"

        key = _issue(client, correo="otro@iieg.mx").json()["api_key"]
        actual = client.get("/v1/api-keys/actual", headers={"Authorization": f"Bearer {key}"})

    assert actual.json()["scopes"] == [auth.SCOPE]


async def test_issuing_is_not_an_mcp_tool():
    """Un agente que se emite sus propias credenciales es exactamente la capacidad que
    este proyecto existe para impedir. Las tools siguen siendo tres."""
    from fastmcp import Client

    from indicadores_sieej.mcp_server import mcp

    async with Client(mcp) as client:
        names = {tool.name for tool in await client.list_tools()}
    assert names == {"listar_indicadores", "describir_indicador", "consultar_indicador"}


# --- La rotación ---


def test_asking_again_rotates_and_kills_the_previous_key(api_keys):
    """Reemitir es la rotación, y también la vía de recuperación de quien perdió la suya.
    Que la anterior siguiera viva convertiría cada recuperación en una key de más."""
    with api_keys.client() as client:
        vieja = _issue(client).json()["api_key"]
        assert _rest(client, vieja).status_code == 200

        nueva = _issue(client).json()["api_key"]
        assert _rest(client, nueva).status_code == 200

        # La vieja sigue en el caché de este proceso hasta que expire su entrada.
        api_keys.clock.advance(61)
        assert _rest(client, vieja).status_code == 401

    activas = [row for row in api_keys.store.rows.values() if row["revoked_at"] is None]
    assert len(activas) == 1


# --- La credencial actual ---


def test_the_current_route_describes_the_key_without_revealing_it(api_keys):
    """No devuelve la key ni su hash. Y no toca la base: todo sale del AccessToken."""
    with api_keys.client() as client:
        key = _issue(client).json()["api_key"]
        headers = {"Authorization": f"Bearer {key}"}
        # Una llamada previa deja la key en el caché del verificador: sin esto se estaría
        # midiendo la consulta de la autenticación, que hace cualquier ruta protegida.
        _rest(client, key)
        antes = api_keys.store.finds
        body = client.get("/v1/api-keys/actual", headers=headers).json()
        sin_consultar = api_keys.store.finds == antes

    assert sin_consultar
    assert body["correo"] == CORREO
    assert body["prefijo"] == key[: registry.PREFIX_LEN]
    assert set(body) == {"correo", "prefijo", "scopes", "emitida_en", "ultimo_uso", "expira_en"}
    assert key not in str(body) and registry.hashed(key) not in str(body)


def test_the_current_route_needs_a_credential(api_keys):
    with api_keys.client() as client:
        assert client.get("/v1/api-keys/actual").status_code == 401


# --- La revocación ---


def test_deleting_the_current_key_leaves_it_unusable_at_once(api_keys):
    """Inmediata en este proceso porque además se desaloja del caché; sin eso seguiría
    sirviendo hasta que expirara su entrada."""
    with api_keys.client() as client:
        key = _issue(client).json()["api_key"]
        headers = {"Authorization": f"Bearer {key}"}

        assert client.delete("/v1/api-keys/actual", headers=headers).status_code == 204
        assert _rest(client, key).status_code == 401
        assert _mcp(client, key).status_code == 401


def test_revoking_only_touches_the_own_key(api_keys):
    """La identidad sale del AccessToken, no del cuerpo: no hay forma de nombrar otra."""
    with api_keys.client() as client:
        mia = _issue(client).json()["api_key"]
        ajena = _issue(client, correo="otro@iieg.mx").json()["api_key"]

        client.delete("/v1/api-keys/actual", headers={"Authorization": f"Bearer {mia}"})
        assert _rest(client, ajena).status_code == 200


# --- Fuera del modo api_key no hay registro que tocar ---


@pytest.mark.parametrize(
    "method, path",
    [("POST", "/v1/api-keys"), ("GET", "/v1/api-keys/actual"), ("DELETE", "/v1/api-keys/actual")],
)
def test_without_the_api_key_mode_the_three_routes_are_503(clients, method, path):
    """Se registran en los tres modos a propósito: condicionar la tabla de rutas a la
    configuración haría que el canario de rutas dependiera del entorno."""
    with clients(TOKEN) as client:
        response = client.request(method, path, json={"correo": CORREO})
    assert response.status_code == 503
    assert response.json()["detail"] == "el registro de API keys no está disponible en este despliegue"


# --- El límite sobre la emisión ---


def test_the_fourth_request_from_one_ip_within_an_hour_is_429(api_keys):
    """Es una ruta pública de escritura y, mientras el correo no se verifique, también un
    primitivo de revocación remota. Sin límite, el abuso se infiere en vez de verse."""
    with api_keys.client() as client:
        codes = [_issue(client, correo=f"c{i}@iieg.mx").status_code for i in range(4)]
    assert codes == [201, 201, 201, 429]


def test_the_limit_lets_go_when_the_hour_passes(api_keys):
    with api_keys.client() as client:
        for i in range(3):
            _issue(client, correo=f"c{i}@iieg.mx")
        assert _issue(client, correo="tarde@iieg.mx").status_code == 429

        api_keys.clock.advance(3601)
        assert _issue(client, correo="tarde@iieg.mx").status_code == 201


def test_the_limit_applies_before_the_body_is_validated(api_keys):
    """Va como dependencia y no dentro del handler justamente por esto: si solo contara
    las peticiones bien formadas, mandar basura saldría gratis."""
    with api_keys.client() as client:
        codes = [_issue(client, correo="no-es-correo").status_code for _ in range(4)]
    assert codes == [400, 400, 400, 429]


def test_the_daily_cap_bounds_the_server_and_not_just_one_origin(api_keys):
    """El de la IP frena a un origen, y una botnet no es un origen."""
    limiter = limits.IssueLimiter(cfg(**API_KEY_MODE, api_key_issue_per_day=2), clock=api_keys.clock)
    limiter.check("10.0.0.1")
    limiter.check("10.0.0.2")

    with pytest.raises(RateLimited):
        limiter.check("10.0.0.3")


def test_the_ip_reaches_the_logs_only_when_the_limit_trips(api_keys, caplog):
    """Es dato personal: en el camino normal no aporta nada que no aporte el conteo."""
    with caplog.at_level(logging.DEBUG):
        with api_keys.client() as client:
            for i in range(3):
                _issue(client, correo=f"c{i}@iieg.mx")
            normal = caplog.text
            _issue(client, correo="tope@iieg.mx")

    assert "testclient" not in normal
    assert "testclient" in caplog.text


def test_the_limiter_does_not_grow_without_bound(api_keys):
    """Las IPs las manda quien pide, así que el diccionario no puede crecer con ellas."""
    limiter = limits.IssueLimiter(cfg(**API_KEY_MODE, api_key_issue_per_day=10**6), clock=api_keys.clock)
    for i in range(limits.SWEEP_AT + 10):
        limiter.check(f"10.0.{i // 256}.{i % 256}")

    api_keys.clock.advance(3601)
    limiter.check("10.9.9.9")
    assert len(limiter._by_ip) == 1


# --- Lo que no se filtra por las rutas nuevas ---


def test_neither_the_key_nor_the_email_reach_the_logs_through_the_new_routes(api_keys, caplog):
    """La key en claro aparece **una sola vez**: en el cuerpo de la emisión. El correo, en
    ninguna: también es dato personal."""
    with caplog.at_level(logging.DEBUG):
        with api_keys.client() as client:
            key = _issue(client).json()["api_key"]
            headers = {"Authorization": f"Bearer {key}"}
            client.get("/v1/api-keys/actual", headers=headers)
            client.delete("/v1/api-keys/actual", headers=headers)

    assert key not in caplog.text
    assert CORREO not in caplog.text
