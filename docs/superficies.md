# Superficies

La misma funcionalidad y el mismo motor, dos transportes, **un solo proceso ASGI**.

## Tools MCP — `/mcp`

Tres tools. Cada una delega **1:1** en el motor: **no hay lógica de negocio en esta capa**. Las tres
se anotan con `readOnlyHint: true` y `openWorldHint: false`.

| Tool                  | Entrada             | Salida                         |
| --------------------- | ------------------- | ------------------------------ |
| `listar_indicadores`  | `tema?`, `nivel?`   | Arreglo de metadata, sin `sql` |
| `describir_indicador` | `id`                | Metadata completa, sin `sql`   |
| `consultar_indicador` | `id`, `parametros?` | Sobre con metadata + filas     |

`listar_indicadores` es el descubrimiento — lo primero que llama un agente. Devuelve una **vista
reducida** (`id`, `nombre`, `tema`, `nivel`, `unidad`, `periodicidad`) para no quemar tokens cuando
el catálogo crezca. Sin coincidencias devuelve lista vacía, no un error.

## Rutas REST — `/v1`

| Método   | Ruta                                  | Equivale a            | Respuesta                             |
| -------- | ------------------------------------- | --------------------- | ------------------------------------- |
| `GET`    | `/v1/indicadores?tema=&nivel=`        | `listar_indicadores`  | `200`                                 |
| `GET`    | `/v1/indicadores/{id}`                | `describir_indicador` | `200` / `404`                         |
| `GET`    | `/v1/indicadores/{id}/datos?<params>` | `consultar_indicador` | `200` / `400` / `413` / `502` / `503` |
| `POST`   | `/v1/api-keys`                        | —                     | `201`, **sin auth** · `400` · `429`   |
| `GET`    | `/v1/api-keys/actual`                 | —                     | `200`                                 |
| `DELETE` | `/v1/api-keys/actual`                 | —                     | `204`                                 |
| `GET`    | `/health`                             | —                     | `200` liveness, **sin auth**          |
| `GET`    | `/ready`                              | —                     | `200` / `503`                         |

Los parámetros del indicador viajan como _query params_ con el **mismo nombre** que declara el YAML.
Un query param no declarado produce **`400`**, no se ignora.

`/ready` sin argumentos no abre pools: reporta el DSN de todos los pipelines y el estado solo de los
ya abiertos. `?pipeline=<p>` fuerza la verificación real de uno.

El OpenAPI se publica en `/docs` y en `/openapi.json`, **autenticados como todo lo demás salvo
`/health`**.

`POST /v1/api-keys` es la **segunda y última ruta que responde sin credencial**, y tiene que serlo:
es de donde sale la primera. A cambio lleva límite por IP y no acepta `scopes` en el cuerpo. Su
excepción está declarada una por una en la prueba que recorre todas las rutas del servidor, así que
abrir una tercera es un diff de una línea que un revisor no puede pasar por alto.

**La emisión no es una tool MCP, y no va a serlo.** Un agente que se emite sus propias credenciales
es exactamente la capacidad que este proyecto existe para impedir. Las tools siguen siendo tres.

El ciclo de vida completo de una API key está en [api-keys.md](api-keys.md).

## El sobre de respuesta

```json
{
  "indicador": "pobreza_municipal",
  "nombre": "Población en situación de pobreza, municipal",
  "unidad": "porcentaje",
  "fuente": "CONEVAL — Medición multidimensional de la pobreza",
  "notas": "Los años disponibles son 2010, 2015 y 2020; no es una serie anual continua.",
  "parametros_aplicados": { "cve_geo": "14039", "anio_min": null },
  "filas": [
    {
      "cve_geo": "14039",
      "nombre_geo": "Guadalajara",
      "periodo": "2010",
      "valor": 26.4,
      "categoria": null
    }
  ]
}
```

- `parametros_aplicados` **incluye los opcionales resueltos a `null`**, para hacer explícito que la
  serie no se filtró por ahí.
- `notas` se entrega **siempre** que exista. Es la letra chica que evita que el agente afirme de más.

## Montaje ASGI — la trampa

Tiene **una sola forma correcta**. Si se omite el `lifespan`, el gestor de sesiones no se inicializa
y el endpoint MCP no funciona:

```python
mcp_app = mcp.http_app(path="/")
app = FastAPI(lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)
```

Y si hace falta CORS, se aplica **por sub-app**, nunca como middleware global: un `CORSMiddleware` de
nivel superior sobre un servidor MCP con OAuth rompe las rutas `.well-known` y las peticiones
`OPTIONS`.

---

Las cinco columnas de `filas`: [contrato-salida.md](contrato-salida.md).
Códigos de error de cada ruta: [errores.md](errores.md).
Autenticación y scopes: [garantias.md](garantias.md).
