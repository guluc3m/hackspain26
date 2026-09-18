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

## Cerrado — decisiones tomadas (W3)

- **Sin generador PDF paralelo**: el intento inicial (report.py con PDF
  escrito a mano) se descartó al llegar el ticket revisado vía main; el
  PDF sale de la plantilla Typst del equipo (`docs/report/`).
- **Datos del store → informe**: `src/albertitos/report_data.py` lee el
  ledger `.sdd/ledger/*.jsonl` y genera `docs/report/datos.typ`
  (`uv run python -m albertitos.report_data`) con bindings #let. Cada
  métrica es una pareja (valor, etiqueta «medido» / «sin datos»); lo no
  medido se declara, jamás se inventa (throughput/coste por factura
  quedan como «sin datos» hasta tener lotes reales).
- **Secciones completadas**: `implementation.typ` (escalera por páginas,
  estado/idempotencia, UI) y `escalabilidad.typ` (tabla de métricas con
  etiqueta medido/sin datos, reparto por extractor, escalado, estimaciones
  marcadas como tales). ADRs: los 4 existentes de la plantilla se mantienen
  (rango 2–5); las decisiones de modelo D-001/D-002 viven en
  `docs/decisiones/DECISIONS.md`.
- **Compilación**: `typst` 0.13.1 instalado user-space en `~/.local/bin`
  (binario estático musl, sin root). `typst compile --font-path fonts
  albertitos_plan.typ` produce 9 páginas con Arquitectura, Implementación,
  Escalabilidad y 4 ADRs. El PDF compilado NO se sube (docs/report/.gitignore).
- **Test**: `tests/test_report_data.py` valida el flujo store→datos.typ con
  ledger sembrado bajo `.sdd/` (el binario typst no participa en tests).
