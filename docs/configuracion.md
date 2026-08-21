# Configuración

Toda por variables de entorno, cargadas con `pydantic-settings` y **validadas al arranque**. Una
configuración inválida o incompleta impide arrancar, con un mensaje que nombra la variable — no falla
más tarde al servir la primera consulta.

| Variable                      |      Oblig.       | Descripción                                        |
| ----------------------------- | :---------------: | -------------------------------------------------- |
| `IIEGDB_DSN_<PIPELINE>`       | Sí (al menos una) | DSN de solo lectura por pipeline catalogado        |
| `IIEGDB_AUTH_MODE`            |        Sí         | `static` \| `jwt`                                  |
| `IIEGDB_STATIC_TOKENS`        |    Condicional    | Tokens y sus scopes, en modo `static`              |
| `IIEGDB_JWKS_URI`             |    Condicional    | Verificación en modo `jwt`                         |
| `IIEGDB_ISSUER`               |    Condicional    | Verificación en modo `jwt`                         |
| `IIEGDB_AUDIENCE`             |    Condicional    | Verificación en modo `jwt`                         |
| `IIEGDB_BASE_URL`             |        Sí         | URL pública del servidor                           |
| `IIEGDB_LIMITE_FILAS`         |        No         | Por defecto `5000`                                 |
| `IIEGDB_STATEMENT_TIMEOUT_MS` |        No         | Por defecto `15000`                                |
| `IIEGDB_RATE_LIMIT`           |        No         | Consultas por minuto y por token; por defecto `60` |
| `IIEGDB_POOL_SIZE`            |        No         | Dimensionamiento por pipeline                      |
| `IIEGDB_POOL_MAX_OVERFLOW`    |        No         | Dimensionamiento por pipeline                      |
| `IIEGDB_LOG_LEVEL`            |        No         | Por defecto `INFO`                                 |

## Secretos

**Los DSN y los tokens nunca se versionan ni se escriben en logs de ningún nivel.** `.env.example`
lleva únicamente placeholders.

> El prefijo `IIEGDB_` viene de la especificación original, redactada cuando el proyecto se llamaba
> `iieg-databases`. Se conserva para no divergir de ella. Si se decide renombrarlo, hay que hacerlo
> aquí, en `.env.example` y en el despliegue, en un solo cambio.

---

Cómo se resuelve el DSN de cada pipeline: [conexiones.md](conexiones.md).
Qué protegen los límites: [garantias.md](garantias.md).
