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

| Tool MCP | Ruta REST | Para qué |
|---|---|---|
| `listar_indicadores` | `GET /v1/indicadores` | Descubrir qué hay |
| `describir_indicador` | `GET /v1/indicadores/{id}` | Ver qué parámetros acepta |
| `consultar_indicador` | `GET /v1/indicadores/{id}/datos` | Traer los datos |

Toda consulta devuelve las mismas cinco columnas —`cve_geo`, `nombre_geo`, `periodo`, `valor`,
`categoria`— que es lo que vuelve intercambiables 33 esquemas distintos. Ver
[docs/contrato-salida.md](docs/contrato-salida.md).

## Correrlo en local

```bash
pip install -e ".[dev]"
pre-commit install --hook-type commit-msg
git config core.hooksPath .githooks

cp .env.example .env      # y llena los DSN
pytest -m "not integration"
python -m indicadores_sieej.cli listar --tema empleo
```

Con Docker, cuando esté disponible:

```bash
docker compose up         # solo necesita el .env
```

## Documentación

El índice de qué leer según lo que vayas a hacer está en **[CLAUDE.md](CLAUDE.md)**. Los documentos
viven en [`docs/`](docs/), uno por pregunta:

[contrato de salida](docs/contrato-salida.md) ·
[anatomía del YAML](docs/anatomia-yaml.md) ·
[reglas del SQL](docs/reglas-sql.md) ·
[periodos y geografía](docs/periodos-y-geografia.md) ·
[validaciones](docs/validaciones-catalogo.md) ·
[errores](docs/errores.md) ·
[garantías de seguridad](docs/garantias.md) ·
[conexiones](docs/conexiones.md) ·
[superficies](docs/superficies.md) ·
[configuración](docs/configuracion.md) ·
[versionado](docs/versionado.md) ·
[decisiones](docs/decisiones.md) ·
[catálogo piloto](docs/catalogo-piloto.md)

## Contribuir

Ver [CONTRIBUTING.md](CONTRIBUTING.md). Todo cambio empieza con un issue.
