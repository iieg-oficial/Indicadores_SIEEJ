# El rol de solo lectura

Cómo se le da acceso al servidor, y qué hay que hacer **cada vez que entra un indicador nuevo**.

La decisión está en [decisiones.md](decisiones.md) (D14): un rol dedicado, `indicadores_ro`, distinto
del que usa ETL-SIEEJ para escribir. Lo crea y custodia el **equipo ETL / DBA**, que es quien tiene
superusuario en el servidor.

## Un rol, no cuatro

En PostgreSQL los roles son del **clúster**, no de la base. Las cuatro bases del piloto viven en el
mismo servidor, así que hay **un** rol y los permisos se otorgan base por base.

Es también lo que ya asume la configuración: `IIEGDB_PG_USER` es uno solo para todas las bases del
servidor por defecto. El día que un pipeline viva en otro servidor, ese clúster necesita su propio
rol homónimo y su `IIEGDB_DSN_<PIPELINE>` — ver [conexiones.md](conexiones.md).

## Qué puede hacer, y qué no

| Puede                                               | No puede                                                |
| --------------------------------------------------- | ------------------------------------------------------- |
| Conectarse a las bases de los pipelines habilitados | Conectarse a cualquier otra base del clúster            |
| `SELECT` sobre las vistas y MV **catalogadas**      | Leer tablas base, ni `public` completo                  |
| —                                                   | Escribir nada, ni `REFRESH MATERIALIZED VIEW`           |
| —                                                   | Mantener una transacción abierta o una consulta colgada |

Es **defensa en profundidad**: estas garantías aplican aunque el servidor tenga un bug. Las del lado
del servidor están en [garantias.md](garantias.md).

## Crear el rol — una vez, en el clúster

```sql
CREATE ROLE indicadores_ro LOGIN PASSWORD '<del gestor de secretos, nunca de este archivo>';

ALTER ROLE indicadores_ro SET default_transaction_read_only = on;
ALTER ROLE indicadores_ro SET statement_timeout = '15s';
ALTER ROLE indicadores_ro SET idle_in_transaction_session_timeout = '30s';
```

Los dos timeouts **duplican a propósito** lo que el servidor ya manda por conexión con
`IIEGDB_STATEMENT_TIMEOUT_MS`. No son redundantes: el `options` de la conexión pisa al del rol en esa
sesión, así que el del rol es la red **por debajo** — lo que queda cuando el servidor no lo manda.
Mantenerlos alineados con el valor del despliegue.

Antes de dar por bueno el alta, revisar qué hereda el rol de `PUBLIC`: si `PUBLIC` conserva `CONNECT`
sobre una base o `USAGE` sobre `public`, el rol puede más de lo que se le otorgó. Revocárselo a
`PUBLIC` afecta a **todo el clúster**, incluido el ETL, así que eso lo decide quien lo administra —
aquí solo queda anotado que hay que mirarlo.

## Otorgar acceso — una vez por base

```sql
\c ilmm
GRANT CONNECT ON DATABASE ilmm TO indicadores_ro;
GRANT USAGE ON SCHEMA public TO indicadores_ro;
GRANT SELECT ON vw_tasa_desocupacion, vw_ocupacion_informal TO indicadores_ro;
```

Las cuatro bases del piloto y los siete objetos que declaran hoy los YAML en su campo `origen`:

| Base (`pipeline`)          | Objetos catalogados                                                   |
| -------------------------- | --------------------------------------------------------------------- |
| `ilmm`                     | `vw_tasa_desocupacion`, `vw_ocupacion_informal`                       |
| `enoe_microdatos`          | `mv_enoe_tasas_jalisco`                                               |
| `delitos_fuero_comun`      | `vw_delitos_serie_historica`, `vw_homicidio_doloso`, `vw_feminicidio` |
| `pobreza_multidimensional` | `vw_pobreza_multidimencional`                                         |

La errata de `multidimencional` está en el nombre real del objeto, no aquí.

**Nunca `GRANT SELECT ON ALL TABLES`, y nunca `ALTER DEFAULT PRIVILEGES`.** Una vista que nadie
catalogó no debe volverse legible sola: el `GRANT` explícito es lo que mantiene la lista de lo
alcanzable igual a la lista de lo catalogado.

## Cuando entra un indicador nuevo

Este es el paso que más se va a repetir, y el que se olvida:

1. El YAML del indicador declara su `origen`. Ese es el objeto que hay que otorgar.
2. **Antes de mergear el PR**, en la base de su `pipeline`:
   `GRANT SELECT ON <origen> TO indicadores_ro;`
3. Si además es un pipeline nuevo: `GRANT CONNECT` sobre esa base, `GRANT USAGE ON SCHEMA public`, y
   agregarlo a `IIEGDB_PIPELINES` en el despliegue.
4. Verificar con las credenciales del rol, no con las de superusuario:
   `psql "<dsn del rol>/<pipeline>" -c 'SELECT 1 FROM <origen> LIMIT 1'`

Va antes del merge porque **el síntoma no se parece a la causa**: sin el `GRANT`, el indicador existe
en el catálogo, aparece en `listar_indicadores` y falla al consultarse con un `502` genérico y una
referencia de correlación. No dice «falta un permiso», y no puede decirlo — el detalle del error de
la base no sale del servidor.

Qué objetos requieren `GRANT` hoy, según el propio catálogo:

```bash
grep -h '^origen:' catalogo/*/*.yaml | sort -u
```

## Verificar el alta

Es el criterio de salida de #24. Con las credenciales del rol:

```sql
SELECT 1 FROM vw_homicidio_doloso LIMIT 1;   -- pasa
SELECT 1 FROM <alguna_tabla_base> LIMIT 1;   -- permission denied
INSERT INTO vw_feminicidio VALUES (...);     -- rechazado: transacción de solo lectura
```

Las tres tienen que dar ese resultado **contra la base**, no contra el servidor: si la tercera falla
por el servidor y no por el rol, el alta no está completa.

## Custodia, rotación y revocación

- La contraseña no se versiona nunca — ver [Qué no se versiona](../CONTRIBUTING.md#qué-no-se-versiona).
  Llega al despliegue por el `.env`, y `.env.example` lleva solo placeholders.
- **Rotarla es una sola edición**, `IIEGDB_PG_PASSWORD`, porque el DSN se arma desde el bloque
  `IIEGDB_PG_*` y no está escrito una vez por base.
- **Revocar el acceso del servidor sin tocar el ETL** es `ALTER ROLE indicadores_ro NOLOGIN`. Esa
  capacidad es justamente lo que se pierde si se reutiliza el usuario del ETL, y es la razón de D14.
- El acceso de red se restringe por `pg_hba.conf` o firewall al host del servidor (SEG-5), que se
  define en #30.

---

Por qué el rol es dedicado: [decisiones.md](decisiones.md) · Cómo se resuelve el DSN:
[conexiones.md](conexiones.md) · Lo que garantiza el servidor: [garantias.md](garantias.md).
