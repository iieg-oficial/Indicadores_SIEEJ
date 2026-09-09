# Configuración

Toda por variables de entorno, cargadas con `pydantic-settings` y **validadas al arranque**. Una
configuración inválida o incompleta impide arrancar, con un mensaje que nombra la variable — no falla
más tarde al servir la primera consulta.

## Variables

### Entorno

| Variable          | Oblig. | Descripción                                     |
| ----------------- | :----: | ----------------------------------------------- |
| `IIEGDB_ENTORNO`  |   No   | `dev` \| `prod`. Por defecto **`prod`**         |

### Conexiones

| Variable                |   Oblig.    | Descripción                                                             |
| ----------------------- | :---------: | ----------------------------------------------------------------------- |
| `IIEGDB_PG_HOST`        |     Sí      | Servidor por defecto: de ahí sale toda base sin DSN propio              |
| `IIEGDB_PG_PORT`        |     No      | Por defecto `5432`                                                      |
| `IIEGDB_PG_USER`        |     Sí      | Rol de solo lectura                                                     |
| `IIEGDB_PG_PASSWORD`    |     Sí      | Sin URL-encodear: no viaja dentro de un DSN                             |
| `IIEGDB_PG_SSLMODE`     |     No      | Por defecto `require` en `prod` y `disable` en `dev`                    |
| `IIEGDB_PIPELINES`      |     Sí      | Pipelines habilitados, separados por comas; `*` para todos              |
| `IIEGDB_DSN_<PIPELINE>` | Condicional | Excepción: la base vive en otro servidor o no se llama como su pipeline |

### Autenticación

| Variable               |   Oblig.    | Descripción                           |
| ---------------------- | :---------: | ------------------------------------- |
| `IIEGDB_AUTH_MODE`     |     Sí      | `api_key` \| `static` \| `jwt`        |
| `IIEGDB_STATIC_TOKENS` | Condicional | Tokens y sus scopes, en modo `static` |
| `IIEGDB_JWKS_URI`      | Condicional | Verificación en modo `jwt`            |
| `IIEGDB_ISSUER`        | Condicional | Verificación en modo `jwt`            |
| `IIEGDB_AUDIENCE`      | Condicional | Verificación en modo `jwt`            |
| `IIEGDB_BASE_URL`      | Condicional | URL pública. Se valida como URL. Obligatoria en `prod` |
| `IIEGDB_REGISTRY_DSN`  | Condicional | Base del registro, en modo `api_key`  |

### Límites y operación

| Variable                      | Oblig. | Descripción                                            |
| ----------------------------- | :----: | ------------------------------------------------------ |
| `IIEGDB_ROW_LIMIT`            |   No   | Por defecto `5000`                                     |
| `IIEGDB_STATEMENT_TIMEOUT_MS` |   No   | Por defecto `15000`                                    |
| `IIEGDB_RATE_LIMIT`           |   No   | Consultas por minuto y por token; por defecto `60`     |
| `IIEGDB_POOL_SIZE`            |   No   | **Por pipeline.** Por defecto `2`                      |
| `IIEGDB_POOL_MAX_OVERFLOW`    |   No   | **Por pipeline.** Por defecto `3`                      |
| `IIEGDB_POOL_TIMEOUT_S`       |   No   | Espera máxima por una conexión libre; por defecto `10` |
| `IIEGDB_LOG_LEVEL`            |   No   | Por defecto `INFO`                                     |

> `POOL_SIZE` y `POOL_MAX_OVERFLOW` son por pipeline, así que se multiplican por la cantidad de
> pipelines en uso. La cuenta que hay que hacer antes de subirlos está en [conexiones.md](conexiones.md#el-presupuesto-de-conexiones).

### Los dos entornos

`IIEGDB_ENTORNO` gobierna **dos defaults y nada más**. No es un interruptor de seguridad: no toca
autenticación, ni límites, ni pools, ni qué pipelines se sirven.

| Variable            | En `prod`                    | En `dev`                |
| ------------------- | ---------------------------- | ----------------------- |
| `IIEGDB_PG_SSLMODE` | `require`                    | `disable`               |
| `IIEGDB_BASE_URL`   | **Obligatoria**, sin default | `http://localhost:8000` |

Son justo las dos que impiden levantar en local o en la red interna: `require` truena si el
PostgreSQL de enfrente no tiene TLS —lo normal puertas adentro— y `base_url` sin valor impide el
arranque. Un valor explícito siempre gana sobre el default del entorno.

**`prod` es el valor por omisión**, y esa dirección es deliberada: olvidar la variable deja el
despliegue endurecido, no relajado. Es el único sentido en el que un olvido sale barato.

**En `prod` no se inventa `base_url`.** Es la URL que el servidor *anuncia* en el handshake de MCP:
adivinar `localhost` no daría un arranque bueno, daría uno que le sirve esa URL a quien está del
otro lado de la red — y eso falla en el cliente, no aquí, que es la peor forma de fallar.

Arrancar en `dev` emite un `WARNING` que nombra lo relajado. `sslmode=disable` es tráfico a la base
**sin cifrar**, y un relajamiento silencioso es el que sobrevive hasta producción.

> El día que el servicio salga de la red interna —#77, ver [decisiones.md](decisiones.md#dónde-vive-el-servicio-y-por-qué-va-sin-tls-d16)—
> el endurecimiento que eso exija (TLS, CORS por sub-app, límites reescalados) va en la rama `prod`
> de esta misma variable. Hoy `prod` es exactamente la conducta de siempre.

### Los tres modos

`api_key` es el de producción: API keys de autoservicio verificadas contra la base propia del
servicio. `static` es para desarrollo. `jwt` queda para el día que exista un proveedor de identidad
institucional. Decidido en #29; el detalle está en [api-keys.md](api-keys.md).

### El registro de API keys

| Variable                           | Oblig. | Descripción                                                          |
| ---------------------------------- | :----: | -------------------------------------------------------------------- |
| `IIEGDB_REGISTRY_DSN`              |   Sí   | DSN completo de la base del registro, con **rol de escritura**       |
| `IIEGDB_API_KEY_TTL_DAYS`          |   No   | Caducidad por desuso; por defecto `90`                               |
| `IIEGDB_API_KEY_TOUCH_S`           |   No   | Cada cuánto se refresca el último uso; por defecto `3600`            |
| `IIEGDB_API_KEY_CACHE_TTL_S`       |   No   | Vida de la key en el caché del proceso; por defecto `60`             |
| `IIEGDB_API_KEY_STALE_S`           |   No   | Cuánto se aguanta un registro caído; por defecto `600`, `0` lo apaga |
| `IIEGDB_API_KEY_ISSUE_PER_IP_HOUR` |   No   | Emisiones por IP y por hora; por defecto `3`                         |
| `IIEGDB_API_KEY_ISSUE_PER_DAY`     |   No   | Tope diario de emisiones del servidor; por defecto `500`             |

> `IIEGDB_REGISTRY_DSN` **no se deriva de `IIEGDB_PG_*`** ni cae de vuelta en él. Ese bloque es el rol
> de **solo lectura** de las 33 bases del ETL; derivar de ahí crearía presión para concederle
> escritura, y eso rompería la garantía de solo lectura en todas a la vez.

**Las tres ventanas tienen que cumplir `CACHE_TTL_S < TOUCH_S < TTL_DAYS`**, y el servidor no arranca
si no. Es lo que hace que una key en uso continuo refresque su último uso antes de caducar: subir el
caché "para bajar carga" haría que una key activa caducara sola, y tardaría noventa días en notarse.

**Los dos topes de emisión son por proceso**, no por despliegue: con varios workers el límite real se
multiplica por su número. Y detrás de un proxy inverso hay que arrancar con
`uvicorn --proxy-headers --forwarded-allow-ips=<ip-del-proxy>`; sin eso todas las peticiones parecen
venir del proxy y el límite por IP se vuelve un límite global. El servidor **no** parsea
`X-Forwarded-For` por su cuenta: confiar en esa cabecera lo haría evadible con un encabezado.

`STALE_S` va aparte porque no es de la misma familia: no ordena el refresco, sino cuánto se sigue
sirviendo una verificación ya hecha mientras el registro no responde. Solo tiene que **durar más que
`CACHE_TTL_S`** —por debajo sería código muerto— y el servidor también lo valida al arrancar.

### El formato de `IIEGDB_STATIC_TOKENS`

Una entrada por consumidor, separadas por comas:

```
<token>:<cliente>:<scope>[ <scope>…]
```

El scope lleva dos puntos dentro, así que la entrada se parte **en tres**: lo que queda después del
segundo `:` es la lista de scopes, separados por espacios. El scope que exige el banco es
`indicadores:read`; un token válido sin él recibe `403`.

```
IIEGDB_STATIC_TOKENS=tok_tableros:tableros:indicadores:read,tok_agente:agente-ia:indicadores:read
```

**Revocar un token es quitar su entrada y reiniciar.** No hay estado que limpiar: los tokens se leen
de aquí y se resuelven una sola vez por proceso.

> ⚠️ En modo `static` los tokens se guardan **en texto plano**. Es lo que pide SEG-7 para un
> despliegue interno con pocos consumidores conocidos, y **no es desplegable en producción**: la
> decisión de pasar a `jwt` o a un verificador contra hashes se toma en #29.

## Secretos

**Los DSN y los tokens nunca se versionan ni se escriben en logs de ningún nivel.** Los `.env.*.example`
llevan únicamente placeholders.

> El prefijo `IIEGDB_` viene de la especificación original, redactada cuando el proyecto se llamaba
> `iieg-databases`. Se conserva para no divergir de ella. Si se decide renombrarlo, hay que hacerlo
> aquí, en los `.env.*.example` y en el despliegue, en un solo cambio.

---

Cómo se resuelve el DSN de cada pipeline: [conexiones.md](conexiones.md).
Qué protegen los límites: [garantias.md](garantias.md).
