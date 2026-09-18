# T6 · Informe de entrega: albertitos_plan.pdf vía plantilla Typst
assignee: W3
priority: p1

## Objetivo
Rellenar la plantilla Typst del equipo (`docs/report/` — `albertitos_plan.typ`,
`lib.typ`, fuentes incluidas) con contenido real medido, y compilar
`albertitos_plan.pdf`. NO crear un generador PDF paralelo desde cero: la
plantilla ya existe (commit 51e39b8, "template para el report").

## Cómo
- Compilación: `typst compile --font-path fonts albertitos_plan.typ` dentro de
  `docs/report/`. El binario `typst` (≥0.13) NO está instalado y no hay root:
  descárgalo de los releases de GitHub (typst-<ver>-x86_64-unknown-linux-musl.tar.xz)
  a `~/.local/bin/` — un solo binario estático, sin dependencias.
- Contenido: completa `implementation.typ` y `escalabilidad.typ` y el bloque de
  ADRs del `albertitos_plan.typ` con datos REALES de `.sdd/` (medidos, no
  inventados; lo estimado va marcado). Los ADRs previstos están en AGENTS.md §13
  y en `docs/decisiones/DECISIONS.md` (úsalo como ADR D-001/D-002 ya escrito).
- Los números (throughput, coste/archivo, latencias) deben salir del store:
  genera un `.typ` de datos desde el store si hace falta, pero no hardcodees.

## Criterios de aceptación
- `albertitos_plan.pdf` se compila desde la plantilla y contiene: arquitectura,
  implementación, escalabilidad y 2–5 ADRs con contexto/alternativas/decisión/
  consecuencias/evidencia.
- Test: el flujo que genera los datos del informe desde el store funciona con
  datos sembrados (el binario typst NO va en tests).
- `uv run pytest` y `uv run ruff check .` en verde.
- No subas el PDF compilado a la solución; el PDF va SOLO al repo de entrega
  (lo prepara el supervisor).
