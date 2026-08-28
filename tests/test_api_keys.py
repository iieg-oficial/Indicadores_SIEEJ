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

from indicadores_sieej import auth, registry
from indicadores_sieej.errors import RegistryUnavailable

from .conftest import API_KEY_MODE, cfg

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
