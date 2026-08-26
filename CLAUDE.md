# Guía de navegación

Este archivo dice **qué leer según lo que vayas a hacer**, para no abrir el repositorio completo.
Cada documento de `docs/` responde una sola pregunta y no repite lo que dice otro.

## Qué es este proyecto

Un catálogo curado de indicadores del IIEG, expuesto como servidor **MCP** (`/mcp`) y **API REST**
(`/v1`) en un mismo proceso ASGI. El agente **nunca** ve el esquema, **nunca** escribe SQL y **nunca**
recibe credenciales de base de datos: elige un indicador del catálogo y le pasa valores a sus
parámetros declarados.

Los datos viven en las 33 bases PostgreSQL de [ETL-SIEEJ](https://github.com/iieg-oficial/ETL-SIEEJ),
una por pipeline. Este proyecto solo **lee**.

## Qué leer según la tarea

| Si vas a…                                     | Lee                                                                                                                                                     |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Agregar o corregir un indicador               | [anatomia-yaml.md](docs/anatomia-yaml.md) → [reglas-sql.md](docs/reglas-sql.md) → [periodos-y-geografia.md](docs/periodos-y-geografia.md)               |
| Dar de alta un flujo nuevo completo           | [nuevo-flujo.md](docs/nuevo-flujo.md)                                                                                                                   |
| Tocar el motor de ejecución                   | [contrato-salida.md](docs/contrato-salida.md) → [reglas-sql.md](docs/reglas-sql.md) → [garantias.md](docs/garantias.md) → [errores.md](docs/errores.md) |
| Tocar la carga del catálogo                   | [validaciones-catalogo.md](docs/validaciones-catalogo.md) → [anatomia-yaml.md](docs/anatomia-yaml.md)                                                   |
| Tocar las tools MCP o las rutas REST          | [superficies.md](docs/superficies.md) → [errores.md](docs/errores.md)                                                                                   |
| Tocar autenticación o límites                 | [garantias.md](docs/garantias.md) → [configuracion.md](docs/configuracion.md)                                                                           |
| Tocar los tokens o su registro                | [tokens.md](docs/tokens.md) → [configuracion.md](docs/configuracion.md)                                                                                 |
| Tocar conexiones o pools                      | [conexiones.md](docs/conexiones.md) → [configuracion.md](docs/configuracion.md)                                                                         |
| Entender por qué algo está así                | [decisiones.md](docs/decisiones.md)                                                                                                                     |
| Saber qué indicadores existen y de dónde leen | [catalogo-piloto.md](docs/catalogo-piloto.md)                                                                                                           |
| Publicar una versión                          | [versionado.md](docs/versionado.md)                                                                                                                     |
| Abrir un PR                                   | [CONTRIBUTING.md](CONTRIBUTING.md)                                                                                                                      |

## Las reglas que nunca se rompen

1. **El campo `sql` no sale del servidor.** Ni en respuestas, ni en errores, ni en logs de nivel
   `INFO` o superior. Hay una prueba automatizada que lo verifica.
2. **Los valores viajan como binds.** Nunca se construye SQL concatenando cadenas ni agregando
   cláusulas `WHERE` según qué parámetros llegaron.
3. **La transacción es de solo lectura**, y el resultado va acotado con `LIMIT`.
4. **El límite falla ruidoso.** Nunca se trunca en silencio: se lanza un error que nombra los
   parámetros con los que acotar.
5. **Agregar un indicador es un YAML y cero líneas de Python.** Si hace falta código, algo está en la
   capa equivocada.

Detalle completo en [garantias.md](docs/garantias.md).

## Estructura

```
src/indicadores_sieej/    el paquete: un módulo por responsabilidad
catalogo/<tema>/<id>.yaml los indicadores
docs/                     un archivo por pregunta
tests/                    sin BD por defecto; las de integración van marcadas
```

## Convenciones

- Python 3.12 · ruff (línea de 120) · pytest con el marker `integration`.
- **Los identificadores del código van en inglés; los comentarios, docstrings, `docs/` y la
  convención de commits, en español.** Se quedan en español tres cosas, porque son contrato y no
  vocabulario: los campos del YAML, las cinco columnas de salida junto con las claves del sobre de
  respuesta, y los subcomandos del CLI.
- Commits: `<tipo>(<scope>): <descripción>`. Solo `feat` y `fix` mueven la versión.
- Archivos cortos y de una sola responsabilidad — tanto en `docs/` como en `src/`.
