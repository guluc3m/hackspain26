# T11 · Compilar albertitos_plan.pdf (plantilla Typst + datos medidos)
assignee: W3
priority: p1

## Objetivo
Producir el PDF real de entrega: `docs/report/albertitos_plan.typ` (plantilla del
equipo, commit 51e39b8) compilado con contenido y números REALES.

## Cómo
1. Binario `typst` (≥0.13) NO está instalado y no hay root: descarga el release
   estático de GitHub (typst-x86_64-unknown-linux-musl.tar.xz) a `~/.local/bin/`.
   Un binario, sin dependencias.
2. Compila: `cd docs/report && typst compile --font-path fonts albertitos_plan.typ`.
3. Rellena `implementation.typ` y `escalabilidad.typ` con los datos de
   `.sdd/metrics/` (T9) y de `.sdd/metrics/corpus-dryrun.json` (T10) — el flujo
   `generar_datos_typ` que ya escribiste. Los ADRs ya bosquejados en
   `albertitos_plan.typ` deben reflejar las decisiones REALES tomadas
   (docs/decisiones/DECISIONS.md + AGENTS.md §13): rung 5 = deepseek-v4.1-flash
   (NO Qwen3.8 — servidor del usuario caído), ERP fuera de scope con costura de
   adaptador, reglas-como-datos v3→v4.
4. Nada hardcodeado: si un número no existe aún en el store (p.ej. files/s del
   runner T8), déjalo como placeholder etiquetado ESTIMADO/PENDIENTE-MEDICIÓN,
   nunca como si fuera medido.

## Criterios de aceptación
- `albertitos_plan.pdf` compila y vive en un artefacto NO commiteado
  (docs/report/.gitignore ya lo ignora): el PDF va SOLO al repo de entrega.
- Test: el flujo de datos .typ se genera desde el store sembrado (el binario no
  va en tests).
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
