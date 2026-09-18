# T16 · UI con datos reales del lote 1 (demo-ready)
assignee: W3
priority: p1

## Objetivo
Tu UI (T5) contra el store REAL del lote 1 — la demo del tribunal, no datos de
siembra. El store con las 500 decisiones está en `/home/deploy/fleet/w1/.sdd/`
(SOLO LECTURA; no lo muevas ni lo copies: tu UI ya lee ledger+store configurables
— apunta las rutas a un symlink `.sdd/lote1` → `/home/deploy/fleet/w1/.sdd` dentro
de tu worktree, o léelo por parámetro, pero NUNCA lo escribas).

## Pantallas a dejar demo-ready (datos reales)
- **Operaciones**: lote 1 = 500 done, 0 fallos, ~8.5 files/s medido, versión de
  reglas v3, rung 4 serializado — lee `.sdd/state/runner.json` + métricas.
- **Facturas**: tabla con los 500 reales: resultado, reglas que decidieron,
  evidencia, latencia, página fuente; filtra por resultado y busca por file_id.
- **Revisión**: los ESCALAR reales (45): imagen de página + lecturas candidatas
  lado a lado, desacuerdo resaltado; aceptar/editar con provenance encolando el
  override (sin tocar el store).
- **Reglas**: regla_v3.yaml real + "qué pasaría si" con umbrales reales.
- **Salud**: estado de llama-server (127.0.0.1:8080 health), drills 4/4 PASS
  (.sdd/metrics/drills.json de T12), reintentos.

## Criterios de aceptación
- Cada pantalla responde 200 con datos reales y renderiza los 45 escalados sin
  bloquear (paginación/scroll virtual si hace falta).
- Test: las 5 pantallas con el store real sembrado (fixture del ledger real
  truncado a 50 filas para velocidad; NO copies .sdd del lote a git).
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
