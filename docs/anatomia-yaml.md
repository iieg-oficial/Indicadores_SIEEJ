# Anatomía del YAML

Un indicador es **un archivo YAML**. Ruta obligatoria:

```
catalogo/<tema>/<id>.yaml
```

con dos invariantes que se validan: **la carpeta se llama igual que el campo `tema`** y **el archivo
(sin extensión) igual que el campo `id`**.

## Campos

| Campo                  | Tipo  | Oblig. | Reglas                                                                                              |
| ---------------------- | ----- | :----: | --------------------------------------------------------------------------------------------------- |
| `id`                   | `str` |   Sí   | Único en todo el catálogo. `snake_case`. Es la clave pública que usa el agente                      |
| `nombre`               | `str` |   Sí   | Título legible                                                                                      |
| `tema`                 | `str` |   Sí   | Igual al nombre de la carpeta. Es la faceta de descubrimiento (`empleo`, `seguridad`, `pobreza`, …) |
| `definicion`           | `str` |   Sí   | Qué mide, en una o dos frases                                                                       |
| `unidad`               | `str` |   Sí   | `porcentaje`, `personas`, `carpetas de investigación`, …                                            |
| `fuente`               | `str` |   Sí   | Institución y programa                                                                              |
| `pipeline`             | `str` |   Sí   | Determina **a qué base se conecta**                                                                 |
| `origen`               | `str` |   Sí   | Vista o MV de la que lee. Solo trazabilidad; no se usa para construir el query                      |
| `nivel`                | enum  |   Sí   | `nacional` \| `estatal` \| `municipal`                                                              |
| `periodicidad`         | `str` |   Sí   | `anual`, `trimestral`, `mensual`, `quinquenal`, …                                                   |
| `cobertura.geografica` | `str` |   Sí   | Ej. `Nacional`, `Jalisco`                                                                           |
| `cobertura.temporal`   | `str` |   Sí   | Ej. `"2017-2024"`. Entre comillas: es texto, no un rango                                            |
| `notas`                | `str` |   No   | Trampas, no comparabilidad, qué **no** es el indicador. Se entrega al agente                        |
| `parametros`           | lista |   No   | Ver abajo. Vacía si el indicador no filtra                                                          |
| `sql`                  | `str` |   Sí   | El query. **Nunca se expone**                                                                       |

### `parametros[]`

| Campo         | Tipo   | Reglas                                                                                               |
| ------------- | ------ | ---------------------------------------------------------------------------------------------------- |
| `nombre`      | `str`  | Debe aparecer como bind `:nombre` en el `sql`, y viceversa — el calce es exacto en ambas direcciones |
| `tipo`        | enum   | `str` \| `int`. Nada más                                                                             |
| `requerido`   | `bool` | Por defecto `false`                                                                                  |
| `descripcion` | `str`  | La lee el agente. **Debe incluir un ejemplo y decir qué pasa si se omite**                           |

## Esquema estricto

Los modelos prohíben campos extra (`extra="forbid"`): una llave mal escrita **revienta al cargar**,
no se ignora en silencio.

**El esquema no se amplía ni se recorta en v1.** Es lo que impide que este catálogo y el que quedó
en ETL-SIEEJ se bifurquen.

## Ejemplo completo

```yaml
id: tasa_desocupacion_municipal
nombre: Tasa de desocupación municipal
tema: empleo
definicion: >
  Porcentaje de la población económicamente activa que se encuentra desocupada,
  estimado a nivel municipal para todos los municipios del país.
unidad: porcentaje
fuente: INEGI — Indicadores del Mercado Laboral Municipal (ILMM)
pipeline: ilmm
origen: vw_tasa_desocupacion
nivel: municipal
periodicidad: anual
cobertura:
  geografica: Nacional
  temporal: "2017-2024"
notas: |
  La vista de origen expone también el error estándar; el banco no lo devuelve
  porque rompería el formato largo.
  No comparable con la tasa estatal de la ENOE: distinto diseño muestral.
parametros:
  - nombre: cve_geo
    tipo: str
    requerido: false
    descripcion: Clave INEGI de 5 dígitos del municipio (ej. 14039). Omitir para todos.
  - nombre: anio_min
    tipo: int
    requerido: false
    descripcion: Año inicial de la serie. Omitir para la serie completa.
sql: |
  SELECT
      clave_municipio::text          AS cve_geo,
      nombre::text                   AS nombre_geo,
      EXTRACT(YEAR FROM fecha)::text AS periodo,
      valor::numeric                 AS valor,
      NULL::text                     AS categoria
  FROM vw_tasa_desocupacion
  WHERE (CAST(:cve_geo AS text) IS NULL
         OR clave_municipio = CAST(:cve_geo AS text))
    AND (CAST(:anio_min AS integer) IS NULL
         OR EXTRACT(YEAR FROM fecha) >= CAST(:anio_min AS integer))
  ORDER BY cve_geo, periodo
```

---

Reglas obligatorias del campo `sql`: [reglas-sql.md](reglas-sql.md).
Qué se verifica al cargar: [validaciones-catalogo.md](validaciones-catalogo.md).
A qué base apunta `pipeline`: [conexiones.md](conexiones.md).
