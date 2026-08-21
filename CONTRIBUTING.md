# Cómo contribuir

## Todo cambio empieza con un issue

Con criterios de aceptación. El backlog está organizado en milestones `F0`–`F4`, y cada issue
declara en su cuerpo de qué otros depende.

Las labels son pocas a propósito: el título del issue es un conventional commit, así que el tipo
y el área ya están ahí. Solo se etiqueta lo que no se deduce del título ni del milestone —
`bloqueante`, `decision` y `repo: etl`. El reparto entre personas se hace con _assignees_.

## Ramas

`main` es la **única rama de integración** y está protegida: no se acepta push directo.

Las ramas de trabajo se nombran `<issue>-<tipo>-<slug>`:

```
1-chore-inicializar-repositorio
6-feat-motor-ejecucion-acotada
```

## Commits

Conventional Commits, **una sola línea**, sin cuerpo:

```
<tipo>(<scope>): <descripción>
```

Tipos: `feat`, `fix`, `update`, `refactor`, `chore`, `docs`, `test`, `ci`, `perf`, `style`, `build`.
Scope opcional: el área afectada (`catalogo`, `motor`, `mcp`, `api`, `auth`, `repo`…).

**Commits atómicos:** un cambio lógico por commit. Si un commit necesita un párrafo para explicarse,
la señal es que debe partirse, no que le falte cuerpo.

Solo `feat` y `fix` aparecen en el CHANGELOG. La versión la decide una persona al publicar,
no el historial de commits — ver [docs/versionado.md](docs/versionado.md).

El hook local lo valida. Instálalo con:

```bash
pre-commit install --hook-type commit-msg
git config core.hooksPath .githooks
```

## Pull requests

- Hacia `main`, con `Closes #N`.
- CI verde. La aprobación se exigirá cuando el repositorio tenga más de un ingeniero activo;
  hoy la protección de `main` solo obliga a los checks.
- Sin `.env`, sin DSN, sin tokens, sin credenciales.
- Un PR que toca `catalogo/` **debería** revisarlo alguien del área temática del indicador, no solo
  desarrollo: el YAML contiene definiciones institucionales, no solo SQL.

## CI

En cada PR corren tres jobs: linter y formato, pruebas sin base de datos, y la validación del
catálogo. Las pruebas marcadas `integration` requieren bases reales y **no** corren en CI.

```bash
pre-commit run --all-files
pytest -m "not integration"
python -m indicadores_sieej.cli validar
```

## Documentación

Un archivo por pregunta, en `docs/`. Si al documentar algo tienes que repetir lo que ya dice otro
documento, enlázalo en vez de copiarlo — el índice está en [CLAUDE.md](CLAUDE.md).
