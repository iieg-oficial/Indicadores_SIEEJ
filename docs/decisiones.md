# Decisiones de arquitectura

Por qué el proyecto está hecho así. Cada una tiene consecuencias que se pagan en otro lado.

|  #  | Decisión               | Elección                                                 | Consecuencia                                                                    |
| :-: | ---------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------- |
| D1  | Framework              | **FastMCP 3.x**                                          | Un solo proceso sirve MCP y REST; auth y middleware ya vienen resueltos         |
| D2  | Transporte MCP         | **Streamable HTTP** en `/mcp`, remoto y multiusuario     | Requiere auth, TLS y despliegue; ningún cliente recibe credenciales de BD       |
| D3  | Superficie doble       | **MCP + REST en el mismo ASGI app**                      | Consumidores no-MCP (tableros, scripts, Power BI) usan REST sin duplicar lógica |
| D4  | Dónde vive el catálogo | **En este repositorio**                                  | Este repo es el dueño único; ETL-SIEEJ no conserva copia editable               |
| D5  | Motor de ejecución     | **Propio**, portado de ETL-SIEEJ                         | Sin dependencia de `core.*` del ETL; el proyecto es autónomo                    |
| D6  | Acceso a datos         | **Conexión directa** a cada base con rol de solo lectura | El servidor necesita red y credenciales; no hay intermediario HTTP              |
| D7  | Contrato de salida     | **Formato largo de 5 columnas**                          | 33 esquemas distintos se vuelven intercambiables para el agente                 |
| D8  | Esquema del YAML       | **Congelado en v1**, con `extra="forbid"`                | Impide que este catálogo y el que quedó en el ETL se bifurquen                  |
| D9  | Verificación de auth   | **Propia**, sobre el `TokenVerifier` de FastMCP          | Un solo lugar decide quién entra; hay que envolver `/mcp` a mano                |

## Por qué la verificación de auth es propia (D9)

FastMCP trae la suya, y sería lo natural. Se descarta por una razón concreta: con `required_scopes`
colapsa el **token válido sin el scope** en un `401`, y [errores.md](errores.md) exige distinguirlo
con un `403` — el cliente que recibe `401` reintenta con otro token, el que recibe `403` sabe que
tiene que pedir permisos.

Lo que sí se usa de FastMCP es el **verificador**: `JWTVerifier` en modo `jwt` y `StaticTokenVerifier`
en `static`. Lo que se escribe aquí es la decisión —401, 403 o pasa—, en una sola función que llaman
las dos superficies: REST como dependencia y MCP como middleware sobre su sub-app.

El precio es que montar `/mcp` sin ese middleware lo dejaría abierto. Lo cubre una prueba que recorre
todas las rutas registradas y verifica que ninguna salvo `/health` responde sin token.

## Por qué un proyecto aparte y no una tool dentro del ETL

ETL-SIEEJ son **33 bases PostgreSQL separadas**, ~198 archivos de migración y ~135 vistas con
esquemas heterogéneos. Dar acceso directo a eso produce SQL malo, cruces equivocados de
`municipio_id` (conviven **tres patrones**) e indicadores inventados.

Este proyecto es el **proxy curado**: la única superficie por la que un agente toca los datos, con un
catálogo revisado por humanos entre medias.

## Lo que está deliberadamente fuera de v1

| Fuera de alcance                                                  | Por qué                                                                      |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Tool de SQL libre, aunque sea de solo lectura                     | Rompe la garantía central: _el agente nunca escribe SQL_                     |
| Exposición del esquema de las bases                               | Mismo motivo; el agente consume indicadores, no esquemas                     |
| Escritura de cualquier tipo, incluido `REFRESH MATERIALIZED VIEW` | Refrescar las MV sigue siendo del `load.py` de cada pipeline en ETL-SIEEJ    |
| Caché de resultados                                               | Optimización prematura; primero se mide                                      |
| Generación de gráficas o archivos                                 | El agente hace eso con las filas que recibe                                  |
| Paginación                                                        | El límite falla ruidoso y el error nombra los filtros; se reevalúa con datos |

## Beneficio operativo

Agregar un indicador nuevo es **escribir un archivo YAML y abrir un PR**. No se toca código Python,
no se despliega lógica nueva, no se le enseña nada al agente.

---

Las garantías que estas decisiones protegen: [garantias.md](garantias.md).
