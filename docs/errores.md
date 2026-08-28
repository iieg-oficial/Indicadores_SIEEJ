# Errores

Los mensajes están redactados para que **el agente pueda corregirse solo**. La capa de transporte los
traduce sin reescribirlos.

| Situación                  | Mensaje                                                  | HTTP |            ¿Recuperable?            |
| -------------------------- | -------------------------------------------------------- | :--: | :---------------------------------: |
| `id` inexistente           | `Indicador '<id>' no existe en el catálogo`              | 404  | Sí — vuelve a `listar_indicadores`  |
| Parámetro no declarado     | `<id>: parámetros desconocidos ['<x>']`                  | 400  | Sí — vuelve a `describir_indicador` |
| Falta parámetro requerido  | `<id>: falta el parámetro requerido '<x>'`               | 400  |                 Sí                  |
| Valor no coaccionable      | error de conversión del tipo                             | 400  |                 Sí                  |
| Excede el límite           | `<id>: la consulta excede 5000 filas; acota con [...]`   | 413  |      Sí — reintenta con filtro      |
| Sin DSN para el pipeline   | `<id>: indicador no disponible en este despliegue`       | 503  |        No — es configuración        |
| Base caída o query fallida | error genérico, **sin el SQL ni el DSN**                 | 502  |                 No                  |
| Sin token o token inválido | `no autenticado` / `token inválido`                      | 401  |                 No                  |
| Token sin el scope         | `el token no tiene el scope 'indicadores:read'`          | 403  |                 No                  |
| Rate limit excedido        | `demasiadas consultas; reintenta en <n>s`                | 429  |           Sí — con espera           |
| Registro de API keys caído | `el registro de API keys no está disponible`             | 503  |      No — reintenta más tarde       |
| Demasiadas emisiones       | `demasiadas solicitudes de API key desde este origen…`   | 429  |      No — reintenta más tarde       |
| Catálogo inválido          | ver [validaciones-catalogo.md](validaciones-catalogo.md) |  —   |       No — impide el arranque       |

## Dos reglas

**Los errores recuperables llegan al agente con su texto íntegro.** La lista de parámetros que trae
el mensaje es justamente lo que le permite reintentar bien. No se resumen ni se reescriben.

**Un registro caído es 503, nunca 401.** Un 401 le diría a cada consumidor que su credencial es
mala y los mandaría a todos a pedir una nueva, convirtiendo un parpadeo del registro en una
estampida contra el registro. El 503 dice lo que pasa: no es la credencial, es el servidor.

**Los errores no recuperables no filtran nada.** Ni SQL, ni DSN, ni credenciales, ni nombres de
tabla, ni trazas de pila. Eso va al log del servidor, con un identificador de correlación que sí se
devuelve al cliente.

## Por qué son excepciones tipadas

La implementación de referencia del ETL usaba un único `ValueError` para todo, lo que obliga a
inspeccionar el texto del mensaje para decidir el código HTTP. Con dos superficies eso no escala:
cada fila de la tabla es una excepción propia, y MCP y REST solo la traducen.

---

Las garantías que estos errores protegen: [garantias.md](garantias.md).
