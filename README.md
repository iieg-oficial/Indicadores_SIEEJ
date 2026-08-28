# Indicadores_SIEEJ

Banco de indicadores del IIEG, expuesto como servidor **MCP** y **API REST** para que agentes de IA y
tableros consulten datos oficiales **sin credenciales de base de datos, sin ver el esquema y sin
escribir una línea de SQL**.

> Estado: en desarrollo — `v0.1 Ajolote`.

## El problema que resuelve

Los datos viven en las **33 bases PostgreSQL** de [ETL-SIEEJ](https://github.com/iieg-oficial/ETL-SIEEJ),
una por pipeline, con ~198 archivos de migración y ~135 vistas de esquemas heterogéneos. Darle eso a
un modelo produce SQL malo, cruces equivocados de `municipio_id` (conviven tres patrones) e
indicadores inventados — cifras inconsistentes presentadas como oficiales.

Este proyecto invierte el orden: **primero un catálogo curado** de consultas pre-hechas,
parametrizadas y descritas en lenguaje natural; **después** una capa que lo expone. El agente elige
un indicador y le pasa valores a sus parámetros declarados.

**Agregar un indicador nuevo es un archivo YAML y cero líneas de Python.**

## Cómo se consulta

Tres tools MCP en `/mcp` y sus rutas REST equivalentes en `/v1`:

| Tool MCP              | Ruta REST                        | Para qué                  |
| --------------------- | -------------------------------- | ------------------------- |
| `listar_indicadores`  | `GET /v1/indicadores`            | Descubrir qué hay         |
| `describir_indicador` | `GET /v1/indicadores/{id}`       | Ver qué parámetros acepta |
| `consultar_indicador` | `GET /v1/indicadores/{id}/datos` | Traer los datos           |

Toda consulta devuelve las mismas cinco columnas —`cve_geo`, `nombre_geo`, `periodo`, `valor`,
`categoria`— que es lo que vuelve intercambiables 33 esquemas distintos. Ver
[docs/contrato-salida.md](docs/contrato-salida.md).

## Correrlo en local

### Con Docker

Levanta el servidor y el PostgreSQL del registro de API keys. No hace falta nada más:

```bash
cp .env.example .env      # sirve tal cual; para leer bases reales, llena IIEGDB_PG_*
docker compose up
```

El `.env.example` arranca en modo `api_key` contra el PostgreSQL que trae `compose.yaml`.
Las 33 bases del ETL viven fuera: sin ruta de red hacia ellas el servidor levanta igual, y sus
indicadores responden `503`.

### Sin Docker

```bash
pip install -e ".[dev]"
pre-commit install --hook-type commit-msg
git config core.hooksPath .githooks

cp .env.example .env      # y llena los DSN
pytest -m "not integration"
python -m indicadores_sieej.cli listar --tema empleo

uvicorn indicadores_sieej.main:app --reload   # MCP en /mcp, REST en /v1, OpenAPI en /docs
```

## Conectar un cliente MCP

Todo lo que responde exige credencial, salvo `/health` y la emisión. Así que el primer paso siempre
es **pedir una API key**, que es de autoservicio: un correo, sin trámite.

```bash
curl -sX POST http://localhost:8000/v1/api-keys \
     -H 'Content-Type: application/json' \
     -d '{"correo":"tu.correo@iieg.mx"}'
```

```json
{
  "api_key": "iieg_a3f9…",
  "correo": "tu.correo@iieg.mx",
  "expira_en": "2026-11-24T18:00:00Z"
}
```

**La key se devuelve una sola vez.** Se guarda solo su hash, así que perderla significa pedir otra —
que además revoca la anterior. Caduca a los 90 días **sin usarse**; una en uso vive indefinidamente.

El transporte es Streamable HTTP y la credencial viaja como bearer token. En Claude Code:

```bash
claude mcp add --transport http indicadores http://localhost:8000/mcp/ \
  --header "Authorization: Bearer iieg_a3f9…"
```

Cualquier otro cliente MCP necesita lo mismo, en su propia sintaxis: la **URL `/mcp/`** —con la barra
final— y el encabezado `Authorization: Bearer <api_key>`. Desde ahí el agente ve las tres tools.

Para un tablero o un script, la misma funcionalidad está en REST con el mismo encabezado:

```bash
curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/v1/indicadores
```

El ciclo de vida completo de la key —rotación, revocación, qué se guarda— está en
[docs/api-keys.md](docs/api-keys.md).

## Agregar un indicador

**Un archivo YAML y cero líneas de Python.** Si hace falta código para que un indicador funcione,
algo está en la capa equivocada.

La guía es [docs/nuevo-flujo.md](docs/nuevo-flujo.md). Si el pipeline ya está dado de alta —que es el
caso normal— se empieza en el **paso 4**; los tres primeros son solo para un pipeline nuevo. Cubre
qué escribir, cómo validarlo en local y qué revisar antes de abrir el PR:

```bash
python -m indicadores_sieej.cli validar               # las siete validaciones del catálogo
python -m indicadores_sieej.cli ejecutar <id> -p cve_geo=14039
```

Dos cosas que producen la mayoría de los errores, y que la guía insiste en dejar dichas:

- **El YAML absorbe la heterogeneidad de las bases.** La columna geográfica cambia según el pipeline
  porque conviven tres patrones de `municipio_id`; el YAML normaliza a `cve_geo` de 5 dígitos y el
  servidor **nunca** adivina la columna.
- **Ausencia de fila no es cero.** Varias vistas de origen descartan ceros y nulos. Si el indicador
  tiene esa trampa, va dicha en `notas` — sin eso, el agente presenta un hueco como un cero.

## Documentación

El índice de qué leer según lo que vayas a hacer está en **[CLAUDE.md](CLAUDE.md)**. Los documentos
viven en [`docs/`](docs/), uno por pregunta:

[dar de alta un flujo nuevo](docs/nuevo-flujo.md) ·
[contrato de salida](docs/contrato-salida.md) ·
[anatomía del YAML](docs/anatomia-yaml.md) ·
[reglas del SQL](docs/reglas-sql.md) ·
[periodos y geografía](docs/periodos-y-geografia.md) ·
[validaciones](docs/validaciones-catalogo.md) ·
[errores](docs/errores.md) ·
[garantías de seguridad](docs/garantias.md) ·
[conexiones](docs/conexiones.md) ·
[superficies](docs/superficies.md) ·
[API keys](docs/api-keys.md) ·
[configuración](docs/configuracion.md) ·
[versionado](docs/versionado.md) ·
[decisiones](docs/decisiones.md) ·
[catálogo piloto](docs/catalogo-piloto.md)

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md). Todo cambio empieza con un issue.
