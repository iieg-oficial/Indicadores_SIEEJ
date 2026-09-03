# Desplegar en la red interna

Cómo se levanta el servicio en un servidor del IIEG, cómo se actualiza y qué revisar cuando algo
falla. La tabla completa de variables está en [configuracion.md](configuracion.md); aquí solo van las
que un despliegue tiene que llenar sí o sí.

## Qué se levanta

`compose.yaml` trae tres servicios y **una sola base propia**:

| Servicio      | Qué es                                                                          |
| ------------- | ------------------------------------------------------------------------------- |
| `registro`    | El PostgreSQL del registro de API keys. La única base que este servicio escribe |
| `migraciones` | Aplica el esquema del registro y termina. Corre antes del servidor, una vez     |
| `servidor`    | El proceso ASGI: MCP en `/mcp`, REST en `/v1`                                   |

Las bases del ETL **viven fuera** y son de solo lectura. Se llega a ellas con `IIEGDB_PG_*`, y un
pipeline sin ruta de red no impide arrancar: sus indicadores responden `503` y el resto sigue
sirviendo.

## Antes de levantarlo

1. **El rol de solo lectura existe y tiene sus `GRANT`.** Es el paso que más se olvida y el que peor
   se diagnostica: sin el `GRANT`, el indicador aparece en el catálogo y falla al consultarse con un
   `502` genérico. Ver [roles-readonly.md](roles-readonly.md).
2. **El host alcanza las cuatro bases del piloto.** Se comprueba antes de desplegar, con un `psql`
   desde el host y las credenciales del rol.
3. **Las pruebas de integración pasan** desde ese host: es lo mismo que va a hacer el servidor.
   Ver [pruebas-integracion.md](pruebas-integracion.md).

## El `.env`

```bash
cp .env.example .env
```

Cuatro valores no se pueden dejar como vienen. Los tres primeros **impiden arrancar** si están mal,
que es la conducta buscada: una configuración incompleta falla al levantar y no al servir la primera
consulta.

| Variable           | Qué va                                                                          |
| ------------------ | ------------------------------------------------------------------------------- |
| `IIEGDB_PG_*`      | Host, usuario y contraseña de `indicadores_ro`. Uno solo para las cuatro bases  |
| `IIEGDB_BASE_URL`  | La URL real del servidor, `http://<host>:<puerto>`. El placeholder no arranca   |
| `IIEGDB_PIPELINES` | Las bases que este despliegue sirve, separadas por comas                        |
| `IIEGDB_AUTH_MODE` | `api_key`. El modo `static` es de desarrollo y guarda los tokens en texto plano |

`IIEGDB_REGISTRY_DSN` **no se toca**: compose lo arma apuntando al `registro` de aquí al lado y gana
sobre el del `.env`.

En la red interna el `sslmode` de las bases del ETL suele ser `disable` o `prefer`; el valor por
defecto es `require` y falla ruidoso si el servidor de PostgreSQL no lo tiene habilitado.

```bash
docker compose up -d
curl -s http://<host>:<puerto>/health     # {"status":"ok","registro":"desconocido"}
```

El `registro` sale `desconocido` hasta que alguien se autentique: su estado es el resultado del
**tráfico real**, no de una sonda, porque `/health` es anónima y sondear desde ahí la volvería un
amplificador de DoS. Después dice `ok` o `caido`.

`/health` es la única ruta sin credencial. Todo lo demás —incluido `/ready` y el OpenAPI de `/docs`—
exige una API key.

## Va sin TLS, a propósito

El servicio se publica en **http dentro de la red del IIEG**, y eso es una decisión —D16 en
[decisiones.md](decisiones.md)—, no un pendiente olvidado. Lo que implica, dicho y no
sobreentendido:

- **Las API keys viajan en `Authorization: Bearer` en claro por la red de la oficina.** Es riesgo
  aceptable para datos públicos institucionales y consumidores internos; deja de serlo el día que el
  servicio salga de esa red.
- **Claude Code se conecta a un `/mcp` en http sin problema.** Claude Desktop y varios conectores
  remotos **exigen `https`**: si alguien lo va a usar desde ahí, hace falta un certificado interno.
- **Nada de esto se expone fuera de la red interna.** Publicarlo hacia afuera es otro despliegue:
  proxy inverso con TLS y `uvicorn --proxy-headers --forwarded-allow-ips=<proxy>`, porque el límite
  de emisión usa `request.client.host` y detrás de un proxy sin eso todas las peticiones parecen
  venir de la misma IP.

## Actualizar

```bash
git pull && docker compose up -d --build
```

**El catálogo va dentro de la imagen, no montado**, así que un indicador nuevo entra al despliegue
solo cuando se reconstruye. Es a propósito: la imagen que corre es exactamente la que se probó.

El servidor **no guarda estado propio**: el catálogo es de solo lectura y el caché de API keys se
reconstruye solo, así que reiniciarlo en cualquier momento es seguro. Las migraciones del registro
corren solas antes del servidor y volver a aplicarlas no hace nada.

El único estado que importa es el volumen `registro_datos`: ahí viven las API keys. Perderlo no
rompe el servicio, pero **todos tienen que pedir su key otra vez**.

## Cuando algo falla

Primero `docker compose logs servidor`, y después esta tabla:

| Síntoma                                               | Qué es                                                                    |
| ----------------------------------------------------- | ------------------------------------------------------------------------- |
| El contenedor no arranca y el log nombra una variable | Configuración incompleta. El mensaje dice cuál                            |
| No arranca y habla del catálogo                       | La imagen se construyó sin `catalogo/`: se cargaron 0 indicadores         |
| `/health` responde y `registro` dice `caido`          | El PostgreSQL del registro está caído: nadie puede emitir ni verificar    |
| Un indicador da `503`                                 | Su pipeline no tiene DSN en este despliegue, o no hay ruta de red         |
| Un indicador da `502` con una referencia              | Falta el `GRANT` sobre su vista, o la vista cambió. El detalle, en el log |
| Todo da `401`                                         | La key caducó por desuso, fue revocada, o falta el `Bearer`               |

`/ready` da el estado por pipeline sin abrir conexiones; `/ready?pipeline=<p>` fuerza la verificación
real de uno solo. Los dos exigen credencial.

Un `502` **nunca** trae el detalle de la base: el `sql` no sale del servidor ni en los errores. La
referencia de correlación que devuelve es lo que permite encontrar la línea en el log.
