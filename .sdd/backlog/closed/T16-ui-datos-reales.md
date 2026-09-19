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

## Cerrado — decisiones tomadas (W3)

- **Lector extendido al formato REAL del runner** (ui/ledger.py): registros
  `event: decision` con `rule_codes` como string ("CODE:PASS,...") se
  parsean a veredictos; `config_version` del runner ⇒ snapshot
  (rule_set_version) para la pantalla Reglas. El `review.jsonl` real
  (kind=fields con candidatos e imágenes) carga tal cual.
- **Store del lote por symlink `.sdd/lote1` → /home/deploy/fleet/w1/.sdd`
  (SOLO LECTURA)**, configurable con `ALBERTITOS_STORE=.sdd/lote1/ledger`.
  Verificado en vivo: 500+ decisiones, 45 ESCALAR, imágenes reales. La cola
  de overrides va SIEMPRE al `.sdd/review-queue/` LOCAL de la UI — jamás se
  escribe en el store externo (regla dura).
- **Operaciones**: tarjeta de estado del runner medido (done/fallos/pendientes,
  4.162 archivos/s, reglas v3.0-2026-09-19, rung 4 serializado con
  llama-server up) desde `state/runner.json`; los huecos del ledger real
  (sin latencia por página, sin coste) se etiquetan honestamente.
- **Facturas**: filtro por resultado + búsqueda por file_id + paginación
  50/página sobre las decisiones reales.
- **Revisión**: cola real paginada (6/página) — 45 escalados renderizan sin
  bloquear; contador de "con imagen disponible" (la cola real solo tiene
  imágenes para parte; el resto degrada con la cadena de evidencia).
- **Reglas**: versión real del snapshot; what-if avisa explícitamente que el
  runner real no registra confianza por campo (sin confianzas medidas).
- **Salud**: llama-server (estado medido por el runner) + drills 4/4 PASS
  (.sdd/metrics/drills.json) + reintentos/omisiones.
- **Tests**: fixture en formato REAL (synthetic, sin depender de W1) + store
  real truncado (50 filas ledger + cola de revisión real con imágenes, bajo
  .sdd/, skip si no existe). El store real es objetivo móvil (W1 sigue
  escribiendo): los tests validan CONSISTENCIA INTERNA del render, no
  números congelados. Demo end-to-end verificada con uvicorn + curl.
- Nota: `test_run.py::test_archivo_con_timeout...` (T8, W2) es flaky de
  timing bajo carga — falla 1 de cada N corridas de suite, verde en
  solitario (3/3); fuera de mi scope, avisado para W2.
- Suite: 163 passed, ruff limpio, sin secretos.
