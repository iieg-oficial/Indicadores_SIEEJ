# API keys

La API es **pública y de autoservicio**: cualquiera pide una API key con su correo y la obtiene, sin
trámite y sin proveedor de identidad. Decidido en #29.

La key no protege el dato — los indicadores son información pública institucional, y eso ya está
aceptado como riesgo residual en [garantias.md](garantias.md). La key **identifica al consumidor**,
que es lo que permite limitarlo y auditarlo.

> **Es una API key, no un token.** Un token en el mundo OAuth y MCP es corto, lo emite un servidor de
> autorización y se refresca. Esto es una credencial larga, opaca, una por consumidor y sin flujo de
> refresco — más cercana a un PAT de GitHub o a una `sk_` de Stripe. Lo que **viaja** en la cabecera
> `Authorization: Bearer` sí es un bearer token: eso es vocabulario de HTTP, y es la única forma que
> acepta el protocolo MCP.

## El ciclo de vida

| Paso       | Qué pasa                                                                                |
| ---------- | --------------------------------------------------------------------------------------- |
| Emisión    | `POST /v1/api-keys` con un correo. La key se devuelve **una sola vez**, en la respuesta |
| Uso        | `Authorization: Bearer <api_key>` en `/mcp` y en `/v1/*`                                |
| Caducidad  | **90 días sin usarse.** No caduca por antigüedad: una en uso vive indefinidamente       |
| Rotación   | Pedir otra para el mismo correo revoca la anterior. Es también la vía de recuperación   |
| Revocación | `DELETE /v1/api-keys/actual` con la key propia                                          |

```bash
curl -sX POST https://<host>/v1/api-keys \
     -H 'Content-Type: application/json' \
     -d '{"correo":"alguien@ejemplo.mx"}'
```

```json
{
  "api_key": "iieg_a3f9…",
  "correo": "alguien@ejemplo.mx",
  "expira_en": "2026-11-24T18:00:00Z"
}
```

## Qué se guarda, y qué no

**La key en claro no se almacena en ninguna parte.** En la base vive su `sha256`, y solo eso.
Perderla significa rotarla; no hay forma de recuperarla.

Se guarda además el correo, un prefijo no secreto —para que soporte la identifique sin conocerla—,
cuándo se emitió, cuándo se usó por última vez y si está revocada. Es lo que le da sustento a la
auditoría por consulta.

El prefijo `iieg_` no es decorativo: hace la key reconocible para un escáner de secretos y permite
identificarla en un ticket sin que nadie tenga que pegar la credencial completa.

### Por qué SHA-256 y no bcrypt

La key es `secrets.token_urlsafe(32)`: 256 bits aleatorios. bcrypt y argon2 encarecen cada intento
para frenar diccionarios contra secretos de **baja entropía**, como una contraseña humana. Contra 256
bits aleatorios no hay diccionario que valga, y el hash está en el camino caliente de **cada
petición**.

**Sin sal, a propósito**: es lo que permite buscar con `WHERE key_hash = :h` por índice. Con sal por
fila habría que hashear y comparar cada fila en cada petición. Y **sin pepper**: una base filtrada
entrega hashes que no se pueden invertir, y un HMAC con llave del servidor añadiría rotación de llaves
sin proteger de nada.

## El correo: hoy es una llave, no una identidad

**El correo no está verificado.** Hoy sirve para una sola cosa: impedir que una misma cuenta acumule
keys. La verificación por correo llega en una fase posterior, y es la que lo convertirá también en
prueba de identidad.

De eso se sigue una consecuencia aceptada a sabiendas: mientras el correo no se verifique,
**cualquiera que conozca una dirección puede revocar la key de esa cuenta** pidiendo una nueva. No
filtra nada —quien lo hace no recibe la key de la víctima, solo la invalida— y la víctima pide otra.
Está en la sección de riesgo residual de [garantias.md](garantias.md).

## La caducidad se mide al verificar

No hay ningún trabajo programado. Cada verificación comprueba que el último uso quepa dentro de la
ventana, y refresca ese último uso de forma acotada — no en cada petición.

Las tres ventanas se configuran, y **el servidor no arranca si el orden se rompe**:

```
IIEGDB_API_KEY_CACHE_TTL_S  <  IIEGDB_API_KEY_TOUCH_S  <  IIEGDB_API_KEY_TTL_DAYS
        60 s                        1 hora                      90 días
```

Ese orden es lo que hace correcta la caducidad por desuso: el caché expira antes que la ventana de
refresco, así que una key en uso continuo siempre refresca su último uso antes de acercarse a los 90
días. Invertirlo —subir el caché para bajar carga, por ejemplo— haría que una key activa caducara
sola, y **tardaría noventa días en notarse**. Por eso se valida al arrancar y no se documenta y ya.

Como el caché vive en el proceso, una revocación tarda como mucho `IIEGDB_API_KEY_CACHE_TTL_S` en
propagarse, y con varios workers eso aplica por worker.

## El registro

Vive en una **base propia de este servicio**, nunca en una de las 33 del ETL: ahí se sigue sin
escribir jamás. Su DSN es su propia variable con su propio rol de escritura y no se deriva de
`IIEGDB_PG_*` — ver [configuracion.md](configuracion.md).

El esquema se aplica **a mano**, nunca al arrancar el servidor:

```bash
python -m indicadores_sieej.cli migrar
```

Se migra con Alembic. Correrlo de nuevo sobre una base al día no hace nada.

---

Qué error devuelve cada situación: [errores.md](errores.md).
Qué protege la autenticación: [garantias.md](garantias.md).
Por qué el registro tiene base propia: [decisiones.md](decisiones.md).
