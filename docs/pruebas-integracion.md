# Las pruebas contra las bases reales

Qué comprueban, cómo se corren y cada cuánto. Son las de `tests/test_integracion.py`, marcadas
`integration` y **opt-in**: no corren en CI, porque CI no tiene ruta de red a las bases del ETL.

## Qué comprueban, y por qué no lo puede comprobar nada más

Todo lo demás del proyecto se prueba con dobles y corre en cada PR. Lo que un doble no puede
demostrar es que el catálogo **corresponda a las bases que existen hoy**:

| Prueba                                | Qué falla si no pasa                                                    |
| ------------------------------------- | ----------------------------------------------------------------------- |
| `test_devuelve_filas`                 | El YAML apunta al vacío: la vista cambió de nombre o se quedó sin datos |
| `test_las_cinco_columnas_en_orden`    | El `SELECT` del YAML dejó de producir el formato largo                  |
| `test_cve_geo_bien_formada`           | La columna geográfica del origen cambió de tipo o de longitud           |
| `test_respeta_el_limite`              | La serie creció y ahora rebasa `IIEGDB_ROW_LIMIT`                       |
| `test_el_filtro_por_municipio_filtra` | El bind opcional no llega a la base: el analista cree que filtró        |
| `test_el_rol_no_puede_escribir`       | El despliegue se conecta con un rol que puede escribir                  |

La primera es la importante: **es la única red que detecta que un `ALTER VIEW` en
[ETL-SIEEJ](https://github.com/iieg-oficial/ETL-SIEEJ) rompió un indicador**. El síntoma en
producción es un `502` con una referencia de correlación, que no dice «la vista cambió» y no puede
decirlo — el detalle del error de la base no sale del servidor.

## Cómo se corren

Hace falta un `.env` con el bloque `IIEGDB_PG_*` apuntando a las cuatro bases del piloto. Los DSN
salen del servidor por defecto, así que es **una** credencial para las cuatro:

```bash
pytest -m integration
```

Sin `.env`, o con uno incompleto, la suite entera hace `skip` en vez de fallar. Un pipeline sin DSN
también: se salta solo el suyo, y el resto sigue corriendo — es lo que la vuelve útil en un
despliegue parcial.

Para correr un indicador solo:

```bash
pytest -m integration -k pobreza_municipal
```

## Las dos que necesitan explicación

**`test_el_rol_no_puede_escribir` falla con tu usuario de siempre, y tiene que fallar.** Comprueba
CA-7 contra la base y no contra el servidor: con `indicadores_ro` creado, la escritura la rechaza el
`default_transaction_read_only` del rol sin que el servidor pida nada. Ver
[roles-readonly.md](roles-readonly.md). Mientras el `.env` lleve un rol que sí puede escribir:

```bash
pytest -m integration -k "not escribir"
```

**Un indicador que rebasa el límite se acota en la prueba, no se le baja el límite.** La constante
`ACOTAR` de `tests/test_integracion.py` lleva los parámetros con los que se consulta cada uno de
esos; hoy solo `incidencia_delictiva_municipal`. Si otro empieza a rebasarlo, se agrega ahí — el
`RowLimitExceeded` ya nombra los parámetros con los que acotar.

## Cada cuánto

- **Antes de mergear un indicador nuevo**, con su `GRANT` ya otorgado — ver
  [nuevo-flujo.md](nuevo-flujo.md).
- **Después de crear o rotar el rol de solo lectura**: si pasan, los `GRANT` están completos.
- **Periódicamente** contra el despliegue, aunque nadie haya tocado este repositorio. Es la única
  forma de enterarse de un cambio en el ETL antes que un analista.
