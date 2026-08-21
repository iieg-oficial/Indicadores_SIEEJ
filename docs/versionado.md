# Versionado

**`vX.Y`**, donde `X` es el major y `Y` el minor release.

**El patch nunca se escribe en cero.** Existe un tercer componente solo cuando hay un _bug fix_ o un
_quick release_ sobre una versión ya publicada.

```
v0.1      primera versión de desarrollo
v0.2      siguiente minor
v0.2.1    quick fix sobre la 0.2
v0.2.2    otro quick fix
v0.3      siguiente minor
```

No existe `v0.2.0`: esa versión se llama `v0.2`. La regla vale en todos lados — el tag, el release,
`pyproject.toml` y `__version__`.

## Los animales

**Cada major lleva asociado un animal endémico de México**, que nombra la serie completa.

| Serie | Animal                               |
| ----- | ------------------------------------ |
| `0.x` | **Ajolote**                          |
| `1.x` | por definir antes de cerrar la `0.x` |

`0.1`, `0.2`, `0.3`… todas son Ajolote. El animal del siguiente major se elige **antes** de cerrar el
anterior, no el día del release.

## Por qué no usamos release-please

Es la herramienta del ETL, y aquí se evaluó y se descartó: **parsea SemVer estricto y siempre escribe
tres componentes**, así que no puede emitir `v0.2` — emitiría `v0.2.0`. Tampoco tiene un tipo de
commit "neutro": cualquier commit convencional le mueve al menos el patch, de modo que un ciclo de
solo documentación acababa proponiendo `0.1.1`.

En su lugar hay dos workflows propios, y **la versión la decide una persona**, no el historial de
commits.

## Cómo se publica

1. **`Preparar release`** (`workflow_dispatch`, se dispara a mano desde Actions). Recibe la versión y
   el animal. Valida el formato —rechaza cualquier cosa que termine en `.0`— actualiza
   `pyproject.toml`, `__version__` y el `CHANGELOG.md`, y abre un PR de release.
2. Se revisa ese PR como cualquier otro y se mergea.
3. **`Publicar release`** detecta el commit `chore(release): vX.Y <Animal>` en `main` y crea el tag
   `vX.Y` y el release de GitHub, titulado `v0.2 Ajolote`.

Qué versión toca es un juicio, no un cálculo: `X.Y` cuando el ciclo trae funcionalidad nueva,
`X.Y.Z` cuando solo se corrige algo de una versión ya publicada.

## Qué aparece en el CHANGELOG

Solo `feat` (Novedades) y `fix` (Correcciones). Los demás tipos —`chore`, `docs`, `test`, `ci`,
`refactor`, `update`, `perf`, `style`, `build`— quedan en el diff del release, no en la lista.

Un ciclo sin `feat` ni `fix` lo dice explícitamente en vez de dejar la entrada vacía.

---

Convención de commits: [../CONTRIBUTING.md](../CONTRIBUTING.md).
