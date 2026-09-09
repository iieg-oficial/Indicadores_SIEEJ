# Conexiones

Cada pipeline tiene **su propia base de datos**. El campo `pipeline` del YAML es lo que decide a cuál
conectarse.

En este proyecto `pipeline` **ya no significa** "carpeta en `core/pipelines/`" como en ETL-SIEEJ: es
la **clave de conexión**. Se conserva el nombre del campo por compatibilidad con el catálogo.

## Resolución del DSN

Hoy son 33 bases y pueden llegar a ser 100. Casi todas viven en el mismo servidor y solo se
distinguen por el nombre de la base — que por convención **es el nombre del pipeline**. Así que la
configuración declara el servidor una vez, y las excepciones una por una:

1. **`IIEGDB_DSN_<PIPELINE>`** (el pipeline en mayúsculas). Si existe, gana. Es para la base que vive
   en otro servidor, o que no se llama como su pipeline.
2. **El servidor por defecto**, si el pipeline está en `IIEGDB_PIPELINES`: se arma el DSN con el
   bloque `IIEGDB_PG_*` y `dbname = <pipeline>`.
3. **Sin DSN**, si no aplica ninguna de las dos.

```
IIEGDB_PG_HOST=10.x.x.x
IIEGDB_PG_USER=indicadores_ro
IIEGDB_PG_PASSWORD=***
IIEGDB_PIPELINES=ilmm,enoe_microdatos,delitos_fuero_comun,pobreza_multidimensional

# La única que se sale de la convención.
IIEGDB_DSN_CONAPO=postgresql://indicadores_ro:***@10.y.y.y:5432/conapo_2024
```

Lo que esto compra: **agregar una base al servidor por defecto no agrega una línea**, y rotar la
contraseña es una sola edición y no 100. De paso, la contraseña deja de tener que ir URL-encodeada
dentro de un DSN.

Los DSN **nunca** se versionan: los `.env.*.example` llevan placeholders.

## Un pool por pipeline, creado en la primera consulta

No una conexión por consulta, ni un pool global único: cada indicador puede vivir en una base
distinta.

Pero **el pool no se abre al arrancar, sino en la primera consulta a ese pipeline**. Con 100
pipelines catalogados y 3 en uso, se mantienen 3 pools. Abrirlos todos al arranque sería pagar por
adelantado cien conexiones que nadie pidió.

El servidor es un **proceso de larga vida**, a diferencia del CLI del ETL. Los pools llevan
`pool_pre_ping=True` y `pool_recycle=3600` como mínimo.

### El presupuesto de conexiones

`IIEGDB_POOL_SIZE` y `IIEGDB_POOL_MAX_OVERFLOW` son **por pipeline**, así que se multiplican:

```
(IIEGDB_POOL_SIZE + IIEGDB_POOL_MAX_OVERFLOW) × pipelines_en_uso ≤ max_connections del servidor
```

Con los valores por defecto —`2` y `3`— caben 20 pipelines simultáneos contra un PostgreSQL de
`max_connections = 100`. Con los valores que traía la especificación original —`5` y `10`— cabrían
seis. **Subirlos sin revisar esta cuenta es lo que tumba el servidor cuando el catálogo crece.**

`IIEGDB_POOL_TIMEOUT_S` acota la espera por una conexión libre: se falla con `503` en vez de
colgar la petición.

## Un pipeline sin DSN no es un error de catálogo

El YAML es válido; simplemente esa base no está disponible en este despliegue.

- El servidor **arranca**.
- Esos indicadores se marcan como **temporalmente no disponibles**.
- Al consultarlos responden **`503`** — no `404`, y no "catálogo roto".

Es lo que permite operar con un subconjunto de las bases, y lo que hace que agregar un pipeline nuevo
al catálogo no rompa los despliegues que aún no lo tienen configurado.

## Salud por pipeline

`/ready` reporta, por pipeline, si tiene DSN resuelto y si su pool responde — y distingue los dos
casos, porque la acción del operador es distinta en cada uno.

**`/ready` no abre pools.** Si lo hiciera, un despliegue con 100 pipelines abriría 100 conexiones
cada vez que el orquestador pregunta. Reporta el DSN de todos y el estado del pool solo de los que ya
están abiertos; `/ready?pipeline=<p>` fuerza la verificación de uno.

**La caída de una base no tumba el servidor:** solo los indicadores de ese pipeline fallan, con `503`
o `502` según corresponda.

---

Cómo se crea y se otorga el rol de lectura: [roles-readonly.md](roles-readonly.md).
Variables de entorno completas: [configuracion.md](configuracion.md).
Códigos de error: [errores.md](errores.md).
