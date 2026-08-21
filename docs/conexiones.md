# Conexiones

Cada pipeline tiene **su propia base de datos**. El campo `pipeline` del YAML es lo que decide a cuál
conectarse.

En este proyecto `pipeline` **ya no significa** "carpeta en `core/pipelines/`" como en ETL-SIEEJ: es
la **clave de conexión**. Se conserva el nombre del campo por compatibilidad con el catálogo.

## Resolución del DSN

Por variable de entorno convencional: `IIEGDB_DSN_` + el `pipeline` en mayúsculas.

```
IIEGDB_DSN_ILMM=postgresql://readonly:***@10.x.x.x:5432/ilmm
IIEGDB_DSN_ENOE_MICRODATOS=...
IIEGDB_DSN_DELITOS_FUERO_COMUN=...
IIEGDB_DSN_POBREZA_MULTIDIMENSIONAL=...
```

Los DSN **nunca** se versionan: `.env.example` lleva placeholders.

## Un pool por pipeline, cacheado

No una conexión por consulta, ni un pool global único: cada indicador puede vivir en una base
distinta.

El servidor es un **proceso de larga vida**, a diferencia del CLI del ETL. Los pools llevan
`pool_pre_ping=True` y `pool_recycle=3600` como mínimo, con `pool_size` y `max_overflow`
dimensionados y documentados.

## Un pipeline sin DSN no es un error de catálogo

El YAML es válido; simplemente esa base no está disponible en este despliegue.

- El servidor **arranca**.
- Esos indicadores se marcan como **temporalmente no disponibles**.
- Al consultarlos responden **`503`** — no `404`, y no "catálogo roto".

Es lo que permite operar con un subconjunto de las bases, y lo que hace que agregar un pipeline nuevo
al catálogo no rompa los despliegues que aún no lo tienen configurado.

## Salud por pipeline

`/ready` reporta, por pipeline, si su DSN está configurado y si el pool responde — y distingue los
dos casos, porque la acción del operador es distinta en cada uno.

**La caída de una base no tumba el servidor:** solo los indicadores de ese pipeline fallan, con `503`
o `502` según corresponda.

---

Variables de entorno completas: [configuracion.md](configuracion.md).
Códigos de error: [errores.md](errores.md).
