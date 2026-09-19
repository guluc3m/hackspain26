# T33-M3 · Regenerar la presentación en un comando (datos siempre actuales)
assignee: W2
priority: p2

## Objetivo
El mp4 (T32) se renderizó con los datos de su momento. `scripts/render_presentacion.sh`
deja en un comando: (1) refresca `presentation/public/datos.json` desde
`.sdd/metrics/` (`uv run python -m albertitos.presentacion`), (2) renderiza
headless con `nice` (no pisar llama-server). Así la presentación siempre sale
con las cifras de la última corrida, sin pasos manuales.

## Cambio
- `scripts/render_presentacion.sh` — wrapper (patrón drill/staging: set -euo,
  cd al repo, nice).
- Test no aplicable al script bash; el feed ya está testeado
  (tests/test_presentacion_datos.py: determinismo + secciones).
