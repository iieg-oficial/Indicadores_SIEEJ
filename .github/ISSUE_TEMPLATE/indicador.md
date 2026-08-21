---
name: Indicador nuevo
about: Solicitar que se catalogue un indicador
title: "feat(catalogo): catalogar "
---

## Qué indicador

**Nombre:**
**Tema:** <!-- empleo | seguridad | pobreza | ... -->
**Nivel:** <!-- nacional | estatal | municipal -->
**Periodicidad:**
**Unidad:**

## De dónde sale

**Pipeline (base de datos):**
**Vista o MV de origen:**
**Fuente institucional:**

## Prerrequisitos de infraestructura

- [ ] `IIEGDB_DSN_<PIPELINE>` configurado
- [ ] Rol de solo lectura con `GRANT SELECT` sobre la vista
- [ ] Ruta de red hacia esa base

## Notas para el agente

<!-- Trampas, no comparabilidad, qué NO es el indicador.
     ¿La vista descarta ceros? Entonces ausencia de fila no es cero: dilo aquí. -->
