# Reglas obligatorias del SQL

Cuatro reglas. Romper cualquiera hace que el indicador falle al cargar o en ejecución.

## 1. Filtros opcionales con `(:param IS NULL OR condición)`

Un **solo** SQL cubre todas las combinaciones de filtros. Nunca se arma el query concatenando
cadenas, ni se agregan cláusulas `WHERE` según qué parámetros llegaron.

```sql
WHERE (CAST(:cve_geo AS text) IS NULL OR clave_municipio = CAST(:cve_geo AS text))
  AND (CAST(:anio_min AS integer) IS NULL OR anio >= CAST(:anio_min AS integer))
```

Los parámetros ausentes se mandan como `NULL` y la condición se neutraliza sola. Como no hay
construcción dinámica de SQL, **no existe superficie de inyección**: los valores viajan siempre como
binds del driver.

## 2. `CAST(:param AS tipo)` en _cada_ aparición

No solo en la primera. Un bind `NULL` sin cast hace que PostgreSQL falle con
_"could not determine data type of parameter $1"_, porque no puede inferir el tipo de un `NULL` suelto.

## 3. Proyectar las cinco columnas con `AS`

Deben aparecer literalmente como `AS cve_geo`, `AS nombre_geo`, `AS periodo`, `AS valor`,
`AS categoria`. Cuando una no aplica, se emite una constante tipada:

```sql
'14'::text   AS cve_geo,      -- indicador estatal fijo
NULL::text   AS categoria     -- indicador sin desagregación
```

## 4. Solo lectura

El SQL debe empezar con `SELECT` o `WITH`. Nada de DDL ni DML en el catálogo.

## Extracción de binds

Para validar el calce `parametros` ↔ `:binds` hay que extraer los binds con un regex que **ignore
los casts de PostgreSQL**:

```python
BINDS = re.compile(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)")
```

El lookbehind negativo `(?<!:)` es lo que impide que `valor::numeric` se lea como un bind llamado
`numeric`. **Sin él, toda validación de parámetros da falsos positivos.**

## Cómo se ejecuta

El SQL del catálogo nunca se ejecuta desnudo. El motor lo envuelve:

```sql
SELECT * FROM ( <sql del catálogo> ) _banco LIMIT <LIMITE + 1>
```

en una transacción de solo lectura y con un `statement_timeout` de sesión. Se pide **una fila de
más** a propósito: si llegan más de `LIMITE`, se lanza un error en vez de devolver una serie
truncada. Ver [garantias.md](garantias.md).

---

Las cinco columnas: [contrato-salida.md](contrato-salida.md).
Formatos de `periodo` y normalización de `cve_geo`: [periodos-y-geografia.md](periodos-y-geografia.md).
