# Dar de alta un flujo nuevo

Cómo pasar de "existe un pipeline en ETL-SIEEJ" a "sus indicadores responden en `/mcp` y en `/v1`".

Los dos repositorios se reparten el trabajo así: **ETL-SIEEJ carga los datos y publica la vista;
aquí solo se cataloga y se expone.** Si un paso pide tocar el esquema, el pipeline o el refresh de
una MV, ese paso no es de este repositorio.

## 1. Qué tiene que existir aguas arriba

- El pipeline **cargado** en ETL-SIEEJ, con su base en el servidor.
- Una **vista o MV que ya entregue el dato agregado**. El `sql` del indicador selecciona, renombra y
  filtra; no agrega.

> Si para llegar al indicador hay que hacer `GROUP BY` sobre datos crudos, la vista está incompleta y
> el arreglo va en ETL-SIEEJ, no aquí. Un indicador que agrega en su `sql` recalcula la cifra en cada
> consulta y se desincroniza de lo que publica el ETL.

**La fuente de verdad del esquema son las migraciones** (`migrations/<pipeline>/sql/`), no los README
de pipeline: varios están desfasados. Los `COMMENT ON` de esas migraciones
(`migrations/<pipeline>/sql/V*__comments_*.sql`) son la materia prima de `definicion` y `notas`.

## 2. Abrir el issue

Plantilla **Indicador nuevo**, uno por indicador. Ahí se decide el `tema`, el `nivel` y de qué vista
sale, antes de escribir nada.

## 3. Dar de alta la conexión

Solo la primera vez que se cataloga algo de ese pipeline:

- Agregar el pipeline a `IIEGDB_PIPELINES` en el `.env` del despliegue.
- `GRANT SELECT` sobre la vista al rol de solo lectura.
- Confirmar la ruta de red hacia esa base.

Si la base **no** está en el servidor por defecto, o no se llama igual que el pipeline, agregar en
cambio su `IIEGDB_DSN_<PIPELINE>`. Detalle en [conexiones.md](conexiones.md).

## 4. Escribir el YAML

Un archivo en `catalogo/<tema>/<id>.yaml`. La carpeta se llama igual que el campo `tema` y el archivo
igual que el campo `id`.

Los campos y sus reglas: [anatomia-yaml.md](anatomia-yaml.md).
Lo que el `sql` está obligado a cumplir: [reglas-sql.md](reglas-sql.md).
Cómo se arman `periodo` y `cve_geo`: [periodos-y-geografia.md](periodos-y-geografia.md).

Lo que más se olvida:

- `notas` es para **lo que el indicador no es**. Si la vista descarta los ceros, decirlo: sin eso, el
  agente presenta una ausencia de fila como un cero.
- `descripcion` de cada parámetro lleva **un ejemplo y qué pasa si se omite**. La lee el agente para
  decidir si lo manda.
- `origen` es trazabilidad, no se usa para construir el query.

**No se toca ni una línea de Python.** Si hace falta código para que el indicador funcione, algo está
en la capa equivocada.

## 5. Validar en local

```bash
python -m indicadores_sieej.cli validar
python -m indicadores_sieej.cli ejecutar <id> -p cve_geo=14039
```

Las siete validaciones y qué mensaje da cada una: [validaciones-catalogo.md](validaciones-catalogo.md).

## 6. Verificar los tres endpoints

El indicador no está dado de alta hasta que las tres superficies lo ven:

| Qué se comprueba             | REST                                           | MCP                   |
| ---------------------------- | ---------------------------------------------- | --------------------- |
| Aparece en el descubrimiento | `GET /v1/indicadores?tema=<tema>`              | `listar_indicadores`  |
| Declara sus parámetros       | `GET /v1/indicadores/<id>`                     | `describir_indicador` |
| Devuelve filas               | `GET /v1/indicadores/<id>/datos?cve_geo=14039` | `consultar_indicador` |

```bash
curl -H "Authorization: Bearer $TOKEN" "$IIEGDB_BASE_URL/v1/indicadores?tema=empleo"
curl -H "Authorization: Bearer $TOKEN" "$IIEGDB_BASE_URL/v1/indicadores/<id>"
curl -H "Authorization: Bearer $TOKEN" "$IIEGDB_BASE_URL/v1/indicadores/<id>/datos?cve_geo=14039"
```

Las filas deben traer las cinco columnas del [contrato de salida](contrato-salida.md), y
`parametros_aplicados` debe listar los opcionales resueltos a `null`.

Si responde **`503`**, el catálogo está bien y la conexión no: revisar el paso 3.
Si responde **`404`**, el `id` no cargó: revisar el paso 5.
El resto de los códigos, en [errores.md](errores.md).

## 7. Abrir el PR

Un PR que toca `catalogo/` **debería** revisarlo alguien del área temática del indicador, no solo
desarrollo: el YAML contiene definiciones institucionales, no solo SQL.

```
- [ ] La vista o MV de origen existe y entrega el dato ya agregado
- [ ] El rol de solo lectura tiene GRANT SELECT sobre ella
- [ ] El pipeline está en IIEGDB_PIPELINES (o tiene su IIEGDB_DSN_<PIPELINE>)
- [ ] El YAML está en catalogo/<tema>/<id>.yaml, carpeta == tema y archivo == id
- [ ] El sql proyecta las cinco columnas con AS y usa (:param IS NULL OR ...) con CAST
- [ ] Las siete validaciones del catálogo pasan
- [ ] Los tres endpoints responden para el id nuevo
- [ ] notas dice qué NO es el indicador, y si la vista descarta ceros
- [ ] Sin .env, DSN ni tokens en el PR
```

---

> **Estado hoy.** Los pasos 5 y 6 todavía no se pueden ejecutar: el CLI y las superficies están
> pendientes en el backlog. Hasta que existan, esta guía sirve para preparar el YAML y la conexión, y
> la verificación queda en revisar el YAML a mano contra
> [validaciones-catalogo.md](validaciones-catalogo.md).

---

Qué indicadores existen ya y de qué vista lee cada uno: [catalogo-piloto.md](catalogo-piloto.md).
