# Versionado

**`vX.Y`**, donde `X` es el major y `Y` el minor release. El tercer componente existe pero **se omite
cuando es cero**: se usa solo para un _quick fix_ sobre una minor ya publicada.

```
v0.1      primera versión de desarrollo
v0.2      siguiente minor
v0.2.1    corrección rápida sobre la 0.2
v0.3      siguiente minor
```

## Los animales

**Cada major lleva asociado un animal endémico de México**, que nombra la serie completa.

| Serie | Animal                               |
| ----- | ------------------------------------ |
| `0.x` | **Ajolote**                          |
| `1.x` | por definir antes de cerrar la `0.x` |

`0.1`, `0.2`, `0.3`… todas son Ajolote. El animal del siguiente major se elige **antes** de cerrar el
anterior, no el día del release.

## Cómo lo produce release-please

El comportamiento **por defecto** antes de `1.0.0` ya produce esta secuencia:

- un commit `feat:` sube la **minor** → `0.1` → `0.2`, el uso normal;
- un commit `fix:` sube el **patch** → `0.2.1`, el quick fix.

Los demás tipos (`chore`, `docs`, `test`, `ci`, `refactor`, `update`, `perf`) no mueven la versión.

> **No activar `bump-patch-for-minor-pre-major`.** Esa opción manda los `feat` al patch y rompería la
> convención, dejando `0.1.1`, `0.1.2` donde deberían ir `0.2`, `0.3`.

`bump-minor-pre-major` sí está activo: evita que un breaking change salte a `1.0` por accidente
durante el desarrollo.

## La diferencia entre versión interna y versión comunicada

release-please parsea SemVer estricto y **siempre** escribe tres componentes, así que el manifest y
`pyproject.toml` llevan `0.1.0`. La versión que se comunica —título del release, encabezado del
CHANGELOG— es `v0.1 Ajolote`.

---

Convención de commits: [../CONTRIBUTING.md](../CONTRIBUTING.md).
