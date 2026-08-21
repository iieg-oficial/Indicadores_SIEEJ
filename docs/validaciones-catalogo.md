# Validaciones del catálogo

Todas corren **al cargar el catálogo**, una sola vez al arrancar el proceso — nunca al servir una
consulta.

> **Un catálogo inválido impide el arranque del servidor**, con un mensaje que nombra el archivo y la
> falla. Nunca degrada en un error servido al usuario en producción.

## Las ocho validaciones

| Validación                                                       | Mensaje de error                                                                                      |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| El YAML valida contra el modelo, sin campos extra                | `campo desconocido '<x>'`                                                                             |
| `id` único en todo el catálogo                                   | `id duplicado '<id>'`                                                                                 |
| Nombre de archivo (sin extensión) == `id`                        | `el id no coincide con el nombre del archivo`                                                         |
| Nombre de carpeta == `tema`                                      | `el tema no coincide con la carpeta`                                                                  |
| `pipeline` declarado en la configuración de conexiones           | `el pipeline '<p>' no está declarado`                                                                 |
| `sql` empieza con `SELECT` o `WITH`                              | `el sql debe empezar con SELECT o WITH`                                                               |
| `sql` proyecta las 5 columnas con `AS`                           | `el sql no proyecta las columnas [...]`                                                               |
| `{parametros}` == `{binds del sql}`, exacto en ambas direcciones | `desajuste entre parametros y binds del sql (declarados sin usar: [...], usados sin declarar: [...])` |

## En tiempo de consulta

Solo quedan las que dependen de los valores recibidos:

- Parámetro **no declarado** ⇒ error. No se ignora.
- Parámetro `requerido` **ausente** ⇒ error.
- Parámetro opcional ausente ⇒ se manda `NULL`, que es lo que neutraliza el filtro.
- Parámetro presente ⇒ se coacciona al `tipo` declarado (`"2020"` → `2020`).

## Gate de CI

`python -m indicadores_sieej.cli validar` corre las ocho y sale con código distinto de cero si algo
falla. Es lo que bloquea todo PR que toque `catalogo/`.

---

Qué campos existen: [anatomia-yaml.md](anatomia-yaml.md).
Qué debe cumplir el `sql`: [reglas-sql.md](reglas-sql.md).
Cómo se traducen estos errores al cliente: [errores.md](errores.md).
