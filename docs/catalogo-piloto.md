# Catálogo piloto

Los **12 indicadores** con los que arranca el catálogo, y a qué vista real lee cada uno.

Los tres temas cubren a propósito las **tres formas de tabla** del repositorio de origen: serie ya
larga (`ilmm`), ancha por mes (`delitos_fuero_comun`) y ancha por concepto
(`pobreza_multidimensional`). Si el formato largo aguanta las tres, aguanta las 33.

## Empleo — 5 indicadores

| `id`                                | Pipeline          | Origen                  | Notas de mapeo                                                                 |
| ----------------------------------- | ----------------- | ----------------------- | ------------------------------------------------------------------------------ |
| `tasa_desocupacion_municipal`       | `ilmm`            | `vw_tasa_desocupacion`  | La MV ya trae `clave_municipio` a 5 dígitos y `nombre`; solo renombrar         |
| `ocupacion_informal_municipal`      | `ilmm`            | `vw_ocupacion_informal` | Igual que el anterior                                                          |
| `tasa_desocupacion_jalisco`         | `enoe_microdatos` | `mv_enoe_tasas_jalisco` | Columna `td`. `cve_geo` fijo `'14'`, `periodo = anio \|\| '-Q' \|\| trimestre` |
| `tasa_informalidad_laboral_jalisco` | `enoe_microdatos` | `mv_enoe_tasas_jalisco` | Columna `til1`                                                                 |
| `tasa_subocupacion_jalisco`         | `enoe_microdatos` | `mv_enoe_tasas_jalisco` | Columna `tsub`                                                                 |

> **Por qué `mv_enoe_tasas` no está catalogada.** La versión municipal agrupa por `entidad_id` pero
> **no lo expone en el SELECT**, solo `municipio_id` (= `cve_mun`, 3 dígitos). No se puede formar una
> `cve_geo` de 5 dígitos a partir de ella. Su índice único `(anio, trimestre, municipio_id)` además
> colisionaría entre estados.

## Seguridad — 3 indicadores

Pipeline `delitos_fuero_comun`. Vista base `vw_delitos_serie_historica`, que ya desapila los 12
meses: `anio, cve_municipio (5 díg. con LPAD), clave_ent, entidad, municipio,
bien_juridico_afectado, tipo_delito, subtipo_delito, modalidad, mes, conteo`.

| `id`                             | Origen                       | Notas de mapeo                                                          |
| -------------------------------- | ---------------------------- | ----------------------------------------------------------------------- |
| `homicidio_doloso_municipal`     | `vw_homicidio_doloso`        | `subtipo_delito = 'Homicidio doloso'`                                   |
| `feminicidio_municipal`          | `vw_feminicidio`             | `tipo_delito = 'Feminicidio'` y `subtipo <> 'Tentativa de feminicidio'` |
| `incidencia_delictiva_municipal` | `vw_delitos_serie_historica` | Parámetro `tipo_delito` → columna `categoria`                           |

El `mes` viene como **nombre en español**; se convierte con `array_position` para armar
`periodo = 'YYYY-MM'` — ver [periodos-y-geografia.md](periodos-y-geografia.md).

## Pobreza — 4 indicadores

Pipeline `pobreza_multidimensional`. Vista `vw_pobreza_multidimencional` **(sic, la errata está en el
nombre real del objeto)**: `cve_mun VARCHAR(5)`, `nombre_municipio`, `cve_ent VARCHAR(2)`,
`nombre_entidad`, `anio SMALLINT` (2010, 2015, 2020) y ~30 columnas anchas `*_porcentaje` /
`*_personas`.

| `id`                              | Columna origen           |
| --------------------------------- | ------------------------ |
| `pobreza_municipal`               | `pobreza_porcentaje`     |
| `pobreza_extrema_municipal`       | `pobreza_ext_porcentaje` |
| `rezago_educativo_municipal`      | `rez_edu_porcentaje`     |
| `carencia_acceso_salud_municipal` | `car_salud_porcentaje`   |

Requieren **unpivot**: cada indicador es un `SELECT` de una columna distinta de la misma vista.
`cve_geo = cve_mun` (ya viene a 5 dígitos), `periodo = anio::text`.

## Las cuatro bases del piloto

`ilmm` · `enoe_microdatos` · `delitos_fuero_comun` · `pobreza_multidimensional`

Cada una necesita su `IIEGDB_DSN_<PIPELINE>` y su rol de solo lectura.

## Trampas que aplican a todo el catálogo

- **Las vistas materializadas necesitan `REFRESH`.** El banco solo lee; el refresh es responsabilidad
  del `load.py` del pipeline en ETL-SIEEJ. Si los datos están viejos, el problema está aguas arriba.
- **Las migraciones son la fuente de verdad**, no los README de pipeline: varios están desfasados. El
  de `ilmm`, por ejemplo, describe tablas que no existen.
- **Los `COMMENT ON`** (17 archivos `migrations/*/sql/V*__comments_*.sql` en ETL-SIEEJ) son la mejor
  materia prima para redactar `definicion` y `notas`: se copia de ahí, no se inventa.

---

Cómo se escribe un YAML: [anatomia-yaml.md](anatomia-yaml.md).
A qué base apunta cada `pipeline`: [conexiones.md](conexiones.md).
