# Decisiones de arquitectura

Por qué el proyecto está hecho así. Cada una tiene consecuencias que se pagan en otro lado.

|  #  | Decisión               | Elección                                                  | Consecuencia                                                                         |
| :-: | ---------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| D1  | Framework              | **FastMCP 3.x**                                           | Un solo proceso sirve MCP y REST; auth y middleware ya vienen resueltos              |
| D2  | Transporte MCP         | **Streamable HTTP** en `/mcp`, remoto y multiusuario      | Requiere auth, TLS y despliegue; ningún cliente recibe credenciales de BD            |
| D3  | Superficie doble       | **MCP + REST en el mismo ASGI app**                       | Consumidores no-MCP (tableros, scripts, Power BI) usan REST sin duplicar lógica      |
| D4  | Dónde vive el catálogo | **En este repositorio**                                   | Este repo es el dueño único; ETL-SIEEJ no conserva copia editable                    |
| D5  | Motor de ejecución     | **Propio**, portado de ETL-SIEEJ                          | Sin dependencia de `core.*` del ETL; el proyecto es autónomo                         |
| D6  | Acceso a datos         | **Conexión directa** a cada base con rol de solo lectura  | El servidor necesita red y credenciales; no hay intermediario HTTP                   |
| D7  | Contrato de salida     | **Formato largo de 5 columnas**                           | 33 esquemas distintos se vuelven intercambiables para el agente                      |
| D8  | Esquema del YAML       | **Congelado en v1**, con `extra="forbid"`                 | Impide que este catálogo y el que quedó en el ETL se bifurquen                       |
| D9  | Verificación de auth   | **Propia**, sobre el `TokenVerifier` de FastMCP           | Un solo lugar decide quién entra; hay que envolver `/mcp` a mano                     |
| D10 | Registro de API keys   | **Base propia**, migrada con Alembic                      | El servicio estrena escritura; ETL-SIEEJ sigue siendo de solo lectura                |
| D11 | Registro caído         | **Se aguanta con caché rancio**, y `/health` lo reporta   | Un parpadeo del registro no debe dejar fuera a todos los consumidores a la vez       |
| D12 | Emisión de API keys    | **Pública, con límite por IP**, y nunca como tool MCP     | Es de donde sale la primera credencial; exigir una sería un círculo                  |
| D13 | Visibilidad del repo   | **Interno**, igual que ETL-SIEEJ                          | Abrirlo publicaría de refilón el esquema de un repositorio que se decidió cerrar     |
| D14 | Rol de lectura         | **Uno dedicado, `indicadores_ro`, con `GRANT` por vista** | Revocar el acceso del servidor no toca al ETL; cada indicador nuevo exige un `GRANT` |
| D15 | Alcance de la API      | **Interna**: no se publica a terceros                     | Sin CORS; los límites se dimensionan para consumidores conocidos del IIEG            |
| D16 | Dónde se despliega     | **Servidor de la red interna, en http, sin TLS**          | Claude Code se conecta a un `/mcp` en http; las keys viajan en claro por esa red     |

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

## Por qué el registro vive en su propia base (D10)

La API se decidió pública y de autoservicio: cualquiera pide una **API key** con su correo y la
obtiene. No es un token: es una credencial larga, opaca, una por consumidor y sin flujo de refresco —
un PAT de GitHub, no un access token. Lo que viaja en `Authorization: Bearer` sí es un bearer token,
que es vocabulario de HTTP y la única forma que acepta MCP.

Eso obliga a **persistir** las keys emitidas, y este servicio nunca había escrito en ningún lado.

La base es **suya**, no una de las 33 del ETL. Sobre aquellas se sigue sin escribir jamás: la
garantía de solo lectura no admite una excepción "pequeña", porque el rol es el mismo para las 33.
Por eso `IIEGDB_REGISTRY_DSN` es su propia variable con su propio rol, y **no** se deriva de
`IIEGDB_PG_*` ni cae de vuelta en él cuando falta: derivarlo crearía presión para concederle
escritura al rol de lectura, y eso rompería la garantía en las 33 bases a la vez.

Se migra con **Alembic** y no con Flyway como ETL-SIEEJ. Es una tabla y este repositorio no tiene
JVM ni `just`; Alembic ya habla con el mismo SQLAlchemy que usa el motor, y los `COMMENT ON` que
exige la convención del ETL salen del propio modelo. El DSN no vive en `alembic.ini` —ese archivo se
versiona— sino que se inyecta desde la configuración, así que servidor y migraciones leen la misma
variable.

**El esquema se aplica a mano**, con `python -m indicadores_sieej.cli migrar`, nunca al arrancar el
servidor. Es la convención del ETL, y significa que el rol del servidor no necesita permisos de DDL
en operación normal.

## Qué pasa cuando el registro no responde (D11)

Con el registro caído, la respuesta obvia —401— es la peor: le diría a cada consumidor que su
credencial es mala y los mandaría a todos a pedir una nueva, convirtiendo un parpadeo en una
estampida contra el registro que acaba de caerse. Por eso es **503**, que dice lo que de verdad pasa.

Aun así, 503 para todos durante una caída es caro cuando el servidor **ya sabe** que esas credenciales
eran buenas hace un minuto. De ahí el caché rancio: durante `IIEGDB_API_KEY_STALE_S` se sigue
sirviendo la última verificación exitosa, y solo esa. Tres límites lo hacen aceptable:

- Solo hay entradas **positivas** en el caché. Una key que ya se supo revocada se desalojó al saberlo,
  y una caída posterior no la resucita.
- Ninguna entrada sobrevive a la caducidad de su propia key.
- Con `IIEGDB_API_KEY_STALE_S=0` la ventana es nula y la caída es 503 desde el primer momento.

Lo que se compra es disponibilidad; lo que se paga es que una revocación tarde hasta esa ventana en
propagarse **durante la caída**. Está en el riesgo residual de [garantias.md](garantias.md).

El estado del registro sale en `/health` y no en `/ready` porque `/ready` exige credencial: con el
registro caído devuelve 503 antes de llegar al handler, y el operador no distingue «registro caído»
de «todo caído». `/health` reporta el **último estado observado** por el tráfico real, sin abrir
ninguna conexión —es la única ruta anónima del servidor, y sondear la base desde ella la convertiría
en un amplificador de DoS— y **sigue respondiendo 200 siempre**: es liveness de este proceso, y un
503 ahí haría que el orquestador reinicie un servidor sano.

## Por qué la emisión es pública y qué se paga por ello (D12)

`POST /v1/api-keys` responde sin credencial porque es de donde sale la primera: exigir una sería un
círculo. Es la **segunda y última** ruta abierta del servidor, y su excepción está declarada una por
una en la prueba que recorre todas las rutas registradas — abrir una tercera es un diff de una línea
que un revisor no puede pasar por alto, en vez de una propiedad emergente de un filtro.

De ahí salen tres restricciones que no se negocian:

- **El cuerpo no acepta `scopes`.** Los pone el servidor. Un campo `scopes` en una petición pública y
  sin autenticar es escalada de privilegios, y es exactamente el campo que alguien va a querer
  agregar "por flexibilidad".
- **La emisión no se expone como tool MCP.** Un agente que se emite sus propias credenciales es la
  capacidad que este proyecto existe para impedir.
- **Lleva límite por IP.** Es una ruta pública de escritura y, mientras el correo no se verifique,
  también un primitivo de revocación remota: pedir una key para un correo ajeno revoca la suya. El
  límite hace que el abuso se vea en vez de inferirse. La IP se registra **solo cuando el límite se
  dispara** —es dato personal— y sale de `request.client.host`, nunca de `X-Forwarded-For`: confiar
  en esa cabecera haría el límite evadible con un encabezado.

Lo que se paga está escrito en el riesgo residual de [garantias.md](garantias.md): hasta que el
correo se verifique, conocer una dirección basta para invalidar la key de esa cuenta.

## Por qué el repositorio es interno (D13)

Cierra la decisión abierta A4. El repositorio nació privado —que es la opción **reversible**: abrirlo
después se puede, y cerrarlo una vez publicado no borra lo que ya se copió o se indexó— y esta
decisión lo confirma en vez de cambiarlo.

La razón **no es el dato**. Que un consumidor autenticado pueda extraer, consulta a consulta, todo el
contenido de los indicadores catalogados ya está aceptado como riesgo residual en
[garantias.md](garantias.md): son información pública institucional. Esta decisión es sobre el
**código y la topología**.

Lo que este repositorio expone y no es público por ningún otro lado son tres cosas: los nombres de
las vistas y MV de origen de cada indicador (`origen` del YAML), los nombres de los pipelines, y la
tabla de los **tres patrones de `municipio_id`** de
[periodos-y-geografia.md](periodos-y-geografia.md) — que es, literalmente, cómo están cruzadas las 33
bases del ETL. Y **ETL-SIEEJ es privado**. Abrir este repositorio publicaría de refilón el esquema de
un repositorio que se decidió mantener cerrado; esa asimetría es la que decide, y es también la que
habría que resolver primero el día que se reconsidere.

No pesa en contra nada de lo que suele forzar la decisión al revés: el repositorio **no versiona
ningún host, IP, DSN ni token real**. Los `.env.*.example` llevan solo placeholders y `alembic.ini` no lleva
`sqlalchemy.url` a propósito, precisamente porque se versiona.

Que sea interno **no relaja el criterio de qué no se versiona**, que está escrito en
[CONTRIBUTING.md](../CONTRIBUTING.md). Por dos razones: un repositorio interno se filtra igual, y la
decisión es reversible — el día que se abra, lo que ya entró a la historia de git no se quita sin
reescribirla.

## Por qué el rol de lectura es dedicado (D14)

Cierra la decisión abierta A5. La alternativa era reutilizar un usuario que ya existe en el servidor:
ahorra el alta de hoy y cobra después en tres lados.

- **Revocar.** Con un rol propio, cortarle el acceso al servidor es `ALTER ROLE ... NOLOGIN`. Con el
  usuario del ETL, cortarlo es parar el ETL.
- **Trazar.** El registro de auditoría dice qué consumidor pidió qué indicador; `pg_stat_activity`
  dice qué conexión abrió la consulta. Con un usuario compartido, la segunda mitad se pierde.
- **La garantía de solo lectura.** El usuario del ETL escribe. Si es el mismo, lo único que impide
  una escritura es el servidor; con un rol en `default_transaction_read_only`, la impide la base
  aunque el servidor tenga un bug.

Lo que se paga es **un `GRANT` por indicador nuevo**, y es el paso que más se va a repetir en cuanto
el catálogo crezca más allá del piloto. Por eso el procedimiento quedó escrito en
[roles-readonly.md](roles-readonly.md) y no solo ejecutado una vez.

Una precisión que cambia el alta: **los roles son del clúster, no de la base**. Como las cuatro bases
del piloto viven en el mismo servidor, no son cuatro roles sino uno con permisos otorgados base por
base — que es lo que ya asumía `IIEGDB_PG_USER`, una sola credencial para todo el servidor por
defecto.

## Hasta dónde llega la API (D15)

Cierra la decisión abierta A6. La API **no se publica a terceros**: sus consumidores son áreas del
IIEG, en la red del instituto.

Conviene no confundir esa decisión con D12, que dice otra cosa. **Que la emisión sea abierta no
significa que el servicio lo sea:** `POST /v1/api-keys` responde sin credencial porque es de donde
sale la primera —exigir una sería un círculo—, pero para llegar a esa ruta hay que estar dentro de la
red donde vive el servicio.

Lo que se sigue de decidir "interna":

- **No se configura CORS.** No hay consumidores web externos, así que no hace falta. El día que los
  haya, va **por sub-app** y nunca como middleware global: un `CORSMiddleware` de nivel superior
  sobre un servidor MCP con OAuth rompe las rutas `.well-known` y las peticiones `OPTIONS`.
- **Los límites se dimensionan para consumidores conocidos**, no para tráfico anónimo de internet.
  Abrirla a terceros obligaría a revisarlos y probablemente a escalonarlos por tipo de consumidor.
- **El OpenAPI es interno.** Se publica autenticado en `/docs`, como el resto salvo `/health`.

Es coherente con D13: el repositorio es interno, y publicar la API expondría de refilón la misma
topología que esa decisión mantiene cerrada.

## Dónde vive el servicio y por qué va sin TLS (D16)

Cierra la decisión abierta A3. El servicio se despliega en un **servidor de la red interna del
IIEG**, con `compose.yaml`, y se publica en **http**.

Lo administra el mismo equipo que administra las bases del ETL, y de ahí se sigue el resto: la ruta
de red hacia las cuatro bases del piloto es directa, los secretos llegan por el `.env` del host —que
no se versiona nunca— y SEG-5 se cumple restringiendo por `pg_hba.conf` o firewall a ese host.

**Que vaya sin TLS es la decisión, no un pendiente.** Los consumidores son áreas del IIEG dentro de
la red del instituto y los datos son públicos institucionales, así que el certificado no compra nada
que la red no dé ya. Lo que se paga, y queda escrito en [despliegue.md](despliegue.md):

- Las API keys viajan en `Authorization: Bearer` **en claro** por la red de la oficina.
- **Claude Code se conecta a un `/mcp` en http sin problema; Claude Desktop y varios conectores
  remotos exigen `https`.** Quien quiera usarlo desde ahí necesita un certificado interno.

Esto matiza a D2, que al elegir Streamable HTTP daba el TLS por supuesto: lo sigue requiriendo el día
que el servicio salga de la red interna, y ese día es #77 — proxy inverso, `--proxy-headers` y
revisar los límites. Es coherente con D15: mientras la API sea interna, la frontera de seguridad es
la red.

**Dónde aterriza #77 cuando llegue: `IIEGDB_ENTORNO=prod`.** La variable existe hoy con un alcance
deliberadamente chico —dos defaults, ver
[configuracion.md](configuracion.md#los-dos-entornos)— y `prod` no endurece nada todavía porque no
hay nada que endurecer: la conducta de `prod` es la de siempre. Es una costura, no una decisión
nueva, y no revierte ni D15 ni D16. Endurecer un servicio contra una apertura que nadie ha
autorizado sería construir contra un requisito imaginario; lo que sí compra tenerla puesta es que
el día que la apertura se decida, el trabajo sea llenar una rama y no rearquitecturar la
configuración.

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
