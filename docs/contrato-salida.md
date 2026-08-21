# Contrato de salida

Toda consulta, sin excepción, devuelve **exactamente estas cinco columnas, en este orden**:

| # | Columna | Tipo | Descripción |
|:-:|---|---|---|
| 1 | `cve_geo` | `text` | Clave INEGI. `'00'` nacional, `'14'` entidad (2 díg.), `'14039'` municipio (5 díg.). Siempre con `LPAD`, nunca numérica |
| 2 | `nombre_geo` | `text` | Nombre oficial de la geografía |
| 3 | `periodo` | `text` | ISO ordenable lexicográficamente: `2024`, `2024-Q1`, `2024-03` |
| 4 | `valor` | `numeric` | El dato. Su unidad vive en la metadata, no en la fila |
| 5 | `categoria` | `text` \| `NULL` | Desagregación opcional: sexo, tipo de delito, actividad. `NULL` cuando el indicador no desagrega |

Ese formato único es lo que hace **intercambiables 33 esquemas distintos**: el agente aprende cinco
columnas una vez y le sirven para todos los indicadores, presentes y futuros.

## La metadata no se repite por fila

Nombre, unidad, fuente, definición y notas viajan **una sola vez** en el sobre de la respuesta.
Repetirlas por fila multiplicaría el costo en tokens del agente sin agregar información.

## Ausencia de fila no es cero

Varias vistas de origen descartan ceros y nulos. Un periodo sin fila **no distingue** "cero eventos"
de "sin dato". Cuando un indicador tiene esa trampa, va dicha en su campo `notas`, y la respuesta
entrega `notas` junto con los datos.

---

Cómo se proyectan estas columnas en el SQL: [reglas-sql.md](reglas-sql.md).
Cómo se construyen `periodo` y `cve_geo`: [periodos-y-geografia.md](periodos-y-geografia.md).
Forma exacta del sobre de respuesta: [superficies.md](superficies.md).
