# Conectar el banco a tu asistente

Guía para el equipo de análisis. Al terminar, tu Claude Code va a poder consultar los indicadores
del IIEG **sin que tú escribas SQL ni tengas credenciales de ninguna base**.

Toma unos cinco minutos y se hace una sola vez.

## Qué es esto

Un catálogo de indicadores ya construidos y revisados —tasa de desocupación, pobreza municipal,
incidencia delictiva— que tu asistente puede consultar directamente. No los inventa ni los calcula:
elige uno del catálogo y le pasa los filtros que tú pidas.

Eso es justamente lo que evita el problema de siempre: un modelo suelto sobre las bases del ETL
escribe cruces equivocados y presenta cifras inconsistentes como oficiales. Aquí no hay forma de
escribir una consulta libre.

## 1. Pide tu clave

Una sola vez, desde cualquier máquina de la red del IIEG:

```bash
curl -sX POST http://<host>:<puerto>/v1/api-keys \
     -H 'Content-Type: application/json' \
     -d '{"correo":"tu.correo@iieg.mx"}'
```

```json
{
  "api_key": "iieg_a3f9…",
  "correo": "tu.correo@iieg.mx",
  "expira_en": "2026-12-02T18:00:00Z"
}
```

**La clave se muestra una sola vez.** Guárdala donde guardas tus contraseñas. Si la pierdes, pides
otra con el mismo correo — y eso revoca la anterior, así que es también la forma de rotarla.

Caduca a los 90 días **sin usarse**. Una que usas seguido no caduca.

## 2. Conéctala

```bash
claude mcp add --scope user --transport http indicadores http://<host>:<puerto>/mcp/ \
  --header "Authorization: Bearer iieg_a3f9…"
```

Tres detalles que son los que fallan cuando algo no funciona:

- La URL termina en **`/mcp/`**, con barra final.
- `--scope user` hace que quede disponible en todos tus proyectos, y solo para ti.
- La clave va completa después de `Bearer `, con el espacio.

Comprueba con `claude mcp list`: debe aparecer `indicadores` como conectado.

## 3. Pregúntale

Ya no hace falta nombrar tools ni ids. Basta con pedirle el dato:

- «¿Cómo va la tasa de desocupación en Jalisco en los últimos cuatro trimestres?»
- «Dame la pobreza municipal de Guadalajara, Zapopan y Tlaquepaque en 2020.»
- «Compara la incidencia delictiva de robo en Guadalajara desde 2020.»
- «¿Qué indicadores de empleo tienes a nivel municipal?»

Por dentro usa tres herramientas, y verlas nombradas ayuda a entender qué está haciendo:

| Herramienta           | Qué hace                                         |
| --------------------- | ------------------------------------------------ |
| `listar_indicadores`  | Descubre qué hay, filtrable por tema y por nivel |
| `describir_indicador` | Qué significa uno y qué filtros acepta           |
| `consultar_indicador` | Trae los datos                                   |

Todo llega en el mismo formato, siempre las mismas cinco columnas —`cve_geo`, `nombre_geo`,
`periodo`, `valor`, `categoria`—, que es lo que permite cruzar indicadores de bases distintas sin
pelearse con los nombres de columna.

## Dos cosas que evitan un reporte equivocado

**Ausencia de fila no es cero.** Varias vistas de origen descartan los ceros y los nulos: si un mes
no aparece, puede significar «no hubo registros» o «no se reportó». Cuando un indicador tiene esa
trampa, la respuesta trae una nota diciéndolo — vale la pena pedirle al asistente que la lea antes
de concluir.

**Si la consulta es demasiado grande, falla en vez de recortar.** No te va a entregar en silencio la
mitad de una serie: te dice con qué filtros acotarla. Un dato incompleto presentado como completo es
peor que un error.

## Si algo no funciona

| Qué ves                                     | Qué pasó                                                                 |
| ------------------------------------------- | ------------------------------------------------------------------------ |
| `401`                                       | La clave está mal pegada, caducó por desuso o fue revocada. Pide otra    |
| `503` en un indicador, los demás funcionan  | Esa base no está incluida en este despliegue todavía                     |
| `502` con una **referencia**                | Falla del lado del servidor: pásale esa referencia a quien lo administra |
| El servidor no aparece en `claude mcp list` | Revisa la barra final de `/mcp/` y que estés en la red del IIEG          |

La referencia del `502` no es adorno: es lo único que permite encontrar qué falló, porque el detalle
del error nunca sale del servidor.

## Lo que no puede hacer, y no va a poder

- **No escribe SQL** ni ve el esquema de las bases.
- **No puede modificar nada**: la conexión es de solo lectura, y el rol de la base tampoco lo
  permitiría.
- **No inventa indicadores.** Si el que necesitas no está, se agrega al catálogo — es un archivo y
  se pide a quien mantiene el banco. Ver [nuevo-flujo.md](nuevo-flujo.md).

## Para un tablero o un script

Lo mismo está en REST, con el mismo encabezado:

```bash
curl -H "Authorization: Bearer $API_KEY" http://<host>:<puerto>/v1/indicadores
curl -H "Authorization: Bearer $API_KEY" \
     "http://<host>:<puerto>/v1/indicadores/pobreza_municipal/datos?cve_geo=14039"
```

El catálogo completo, indicador por indicador y con su fuente, está en
[catalogo-piloto.md](catalogo-piloto.md).
