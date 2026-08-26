# Garantías de seguridad

Cinco garantías del servidor. **Perder cualquiera convierte el proyecto en una consola SQL abierta a
un modelo de lenguaje.** Ninguna es negociable.

|  #  | Garantía                              | Cómo se preserva                                                                                          |
| :-: | ------------------------------------- | --------------------------------------------------------------------------------------------------------- |
|  1  | El agente **nunca ve** el SQL         | La metadata que sale al exterior es el YAML **sin** el campo `sql`; tampoco aparece en errores ni en logs |
|  2  | El agente **nunca escribe** SQL       | La única entrada libre son los **valores** de los parámetros declarados                                   |
|  3  | Los valores viajan como **binds**     | Nunca interpolación de cadenas — ver [reglas-sql.md](reglas-sql.md)                                       |
|  4  | La transacción es de **solo lectura** | `execution_options(postgresql_readonly=True)` / `SET TRANSACTION READ ONLY`                               |
|  5  | El resultado está **acotado**         | `LIMIT <LIMITE+1>` y error ruidoso al excederlo                                                           |

## El límite falla ruidoso, no trunca en silencio

`LIMITE = 5000` por defecto, configurable. Se piden `LIMITE + 1` filas; si llegan más, **se lanza un
error** que nombra los parámetros disponibles para acotar:

```
incidencia_delictiva_municipal: la consulta excede 5000 filas;
acota con ['anio_min', 'cve_geo', 'tipo_delito']
```

Devolver 5000 filas de una serie de 40000 sin decirlo es **peor que fallar**: el agente reporta como
completa una serie cortada. Ese mensaje es accionable — el agente reintenta con un filtro.

## Defensa en profundidad en la base de datos

Las cinco anteriores son del servidor. Estas son de PostgreSQL y aplican **aunque el servidor tenga
un bug**:

- Cada base catalogada tiene un **rol dedicado de solo lectura**, con `GRANT SELECT` **únicamente
  sobre las vistas y MV catalogadas** — no sobre las tablas base, no sobre `public` completo.
- El rol lleva `ALTER ROLE ... SET default_transaction_read_only = on`.
- El rol lleva `statement_timeout` e `idle_in_transaction_session_timeout` fijados a nivel de rol.
- Sus credenciales **no** son las que usa el ETL para escribir.
- El acceso de red se restringe por firewall o `pg_hba.conf` al host del servidor.

## Autenticación

Ninguna ruta salvo `/health` responde sin autenticación válida — ni `/mcp`, ni `/v1/*`, ni `/ready`,
ni el propio `/docs`. El scope requerido es **`indicadores:read`**; una credencial sin él recibe `403`.

MCP y REST **comparten la misma verificación**: una sola función decide quién entra, y las dos
superficies la llaman. Dos implementaciones distintas de auth en el mismo proceso es cómo se abre un
agujero. Lo verifica una prueba que recorre **todas** las rutas registradas del app: si alguien
agrega una por fuera del router, falla.

Cada credencial identifica a **un** consumidor. Es lo que hace útil la auditoría.

Cómo se emiten y se revocan las API keys: [api-keys.md](api-keys.md).

Por qué la verificación es propia y no la de FastMCP: [decisiones.md](decisiones.md).

## Qué se acepta como riesgo residual

Un consumidor autenticado puede extraer, consulta a consulta, todo el contenido de los indicadores
catalogados. **Eso es correcto y deseado**: los indicadores son información pública institucional. El
control no está en ocultar los datos, sino en que **solo se expone lo curado**, con su definición,
unidad, fuente y notas al lado.

---

Tabla completa de errores: [errores.md](errores.md).
Variables que ajustan los límites: [configuracion.md](configuracion.md).
