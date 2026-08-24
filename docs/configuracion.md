# Configuración

Toda por variables de entorno, cargadas con `pydantic-settings` y **validadas al arranque**. Una
configuración inválida o incompleta impide arrancar, con un mensaje que nombra la variable — no falla
más tarde al servir la primera consulta.

## Variables

### Conexiones

| Variable                |   Oblig.    | Descripción                                                             |
| ----------------------- | :---------: | ----------------------------------------------------------------------- |
| `IIEGDB_PG_HOST`        |     Sí      | Servidor por defecto: de ahí sale toda base sin DSN propio              |
| `IIEGDB_PG_PORT`        |     No      | Por defecto `5432`                                                      |
| `IIEGDB_PG_USER`        |     Sí      | Rol de solo lectura                                                     |
| `IIEGDB_PG_PASSWORD`    |     Sí      | Sin URL-encodear: no viaja dentro de un DSN                             |
| `IIEGDB_PG_SSLMODE`     |     No      | Por defecto `require`                                                   |
| `IIEGDB_PIPELINES`      |     Sí      | Pipelines habilitados, separados por comas; `*` para todos              |
| `IIEGDB_DSN_<PIPELINE>` | Condicional | Excepción: la base vive en otro servidor o no se llama como su pipeline |

### Autenticación

| Variable               |   Oblig.    | Descripción                           |
| ---------------------- | :---------: | ------------------------------------- |
| `IIEGDB_AUTH_MODE`     |     Sí      | `static` \| `jwt`                     |
| `IIEGDB_STATIC_TOKENS` | Condicional | Tokens y sus scopes, en modo `static` |
| `IIEGDB_JWKS_URI`      | Condicional | Verificación en modo `jwt`            |
| `IIEGDB_ISSUER`        | Condicional | Verificación en modo `jwt`            |
| `IIEGDB_AUDIENCE`      | Condicional | Verificación en modo `jwt`            |
| `IIEGDB_BASE_URL`      |     Sí      | URL pública del servidor              |

### Límites y operación

| Variable                      | Oblig. | Descripción                                            |
| ----------------------------- | :----: | ------------------------------------------------------ |
| `IIEGDB_LIMITE_FILAS`         |   No   | Por defecto `5000`                                     |
| `IIEGDB_STATEMENT_TIMEOUT_MS` |   No   | Por defecto `15000`                                    |
| `IIEGDB_RATE_LIMIT`           |   No   | Consultas por minuto y por token; por defecto `60`     |
| `IIEGDB_POOL_SIZE`            |   No   | **Por pipeline.** Por defecto `2`                      |
| `IIEGDB_POOL_MAX_OVERFLOW`    |   No   | **Por pipeline.** Por defecto `3`                      |
| `IIEGDB_POOL_TIMEOUT_S`       |   No   | Espera máxima por una conexión libre; por defecto `10` |
| `IIEGDB_LOG_LEVEL`            |   No   | Por defecto `INFO`                                     |

> `POOL_SIZE` y `POOL_MAX_OVERFLOW` son por pipeline, así que se multiplican por la cantidad de
> pipelines en uso. La cuenta que hay que hacer antes de subirlos está en [conexiones.md](conexiones.md#el-presupuesto-de-conexiones).

## Secretos

**Los DSN y los tokens nunca se versionan ni se escriben en logs de ningún nivel.** `.env.example`
lleva únicamente placeholders.

> El prefijo `IIEGDB_` viene de la especificación original, redactada cuando el proyecto se llamaba
> `iieg-databases`. Se conserva para no divergir de ella. Si se decide renombrarlo, hay que hacerlo
> aquí, en `.env.example` y en el despliegue, en un solo cambio.

---

Cómo se resuelve el DSN de cada pipeline: [conexiones.md](conexiones.md).
Qué protegen los límites: [garantias.md](garantias.md).
