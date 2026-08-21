# Periodos y geografía

Es lo que el agente pregunta siempre: *"dame X en el municipio Y para el periodo Z"*. El banco lo
resuelve **dentro del SQL de cada YAML**, no en la capa que lo envuelve.

## Construcción de `periodo`

Siempre `text`, y el formato depende de la forma de la fuente:

| Periodicidad | Formato | Construcción típica |
|---|---|---|
| Anual | `2024` | `EXTRACT(YEAR FROM fecha)::text` o `anio::text` |
| Trimestral | `2024-Q1` | `anio::text \|\| '-Q' \|\| trimestre::text` |
| Mensual | `2024-03` | `anio::text \|\| '-' \|\| LPAD(<mes>::text, 2, '0')` |
| Quinquenal | `2020` | `anio::text` |

El formato es lexicográficamente ordenable, así que ordenar por `periodo` como texto ordena
cronológicamente.

**Caso real que conviene conocer:** el SESNSP publica el mes **como nombre en español**, así que el
YAML lo convierte a número dentro del SQL:

```sql
anio::text || '-' || LPAD(array_position(
    ARRAY['Enero','Febrero','Marzo','Abril','Mayo','Junio',
          'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre'],
    mes)::text, 2, '0')  AS periodo
```

## Filtrado temporal

**Un solo parámetro convencional: `anio_min` (`int`, opcional).** Recorta la serie por el extremo
inferior.

Deliberadamente **no** existen en v1: `anio_max`, rangos de fechas, ni filtro por `periodo` exacto.
El agente pide la serie y la recorta él; el catálogo no crece en superficie. Si se agregan, se
agregan como parámetro nuevo en los YAML — **no** como lógica en el servidor.

## Filtrado geográfico

**Un solo parámetro convencional: `cve_geo` (`str`, opcional)**, la clave INEGI de 5 dígitos del
municipio. Omitirlo devuelve todos.

Los indicadores de nivel `estatal` o `nacional` normalmente **no declaran `cve_geo`**: emiten la
clave como constante (`'14'::text AS cve_geo`). Que un parámetro exista o no es información que el
agente obtiene de la metadata, no que deba suponer.

## Los tres patrones de `municipio_id`

La columna de origen **cambia según el pipeline**, porque en ETL-SIEEJ conviven tres patrones de
JOIN. **El YAML absorbe esa heterogeneidad**: normaliza a `cve_geo` de 5 dígitos con `LPAD` y expone
siempre el mismo nombre de parámetro. El servidor **nunca** intenta adivinar la columna.

| Patrón | JOIN en el origen | Pipelines |
|---|---|---|
| Compuesto | `m.cve_mun = x.municipio_id AND m.cve_ent = x.entidad_id` | agropecuario_siap, censo_poblacion, censos_economicos, centros_educativos, denue, escuelas, establecimientos_de_salud, participacion_ciudadana, produccion_ganadera, enoe_microdatos, fiscalia |
| CVEGEO directo (5 díg.) | `m.cvegeo = x.municipio_id` | conapo, intensidad_migratoria, marginacion, nacimientos_dgis, delitos_fuero_comun (`::INTEGER`), efipem (`LPAD(...,5,'0')`) |
| Surrogate key | `m.id = x.municipio_id` | defunciones, repd |

`entidad_id` sí es consistente: siempre contra `cvegeo_states.cve_ent`.

> Usar el patrón equivocado produce cruces **silenciosamente incorrectos**: no falla, devuelve datos
> de otro municipio.

---

Las cinco columnas: [contrato-salida.md](contrato-salida.md).
Cómo se escriben los filtros: [reglas-sql.md](reglas-sql.md).
