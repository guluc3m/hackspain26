# T8 · Runner de lote: los 500 PDFs end-to-end
assignee: W2
priority: p0

## Objetivo
`src/albertitos/run.py` + `python -m albertitos.run` — orquesta el pipeline
completo sobre el corpus real y emite `outcomes.jsonl`. Es el punto donde T1
(extracción) + T2 (parser) + T3 (reglas) + T4 (store) se convierten en producto.

## Flujo
1. Enumera `caja-de-alberto/facturas/*.pdf` (500) — `file_id` = basename EXACTO.
2. Por archivo: sha256 → ledger (idempotencia) → escalera por página (T1) →
   parser (T2) → motor de reglas (T3) → decisión → store + evidencia (T4).
3. Serialización de rung 4: si llama-server está corriendo
   (`http://127.0.0.1:8080`, health-check primero), el rung 4 va en cola
   SECUENCIAL (una página cada vez, `--threads` ya limitado) — nunca en
   paralelo con el resto: 8 cores compartidos con el ERP y la flota.
4. Reanudable: saltar lo completado (cache+ledger); `--limit N` y `--only <glob>`
   para pruebas parciales; crash a mitad ⇒ re-run completa sin duplicados.
5. Emisión final: `outcomes.jsonl` (una línea por factura, file_id exacto,
   result ∈ PAGAR/NO_PAGAR/ESCALAR + traza opcional) + validador (T9) en verde.

## Reglas duras
- NUNCA tocar archivos de `caja-de-alberto/` (solo lectura).
- Timeout por archivo (config); un archivo colgado no para el lote: timeout ⇒
  ESCALAR con motivo `timeout` y evidencia, y se sigue.
- Concurrencia: máximo 2 archivos en vuelo (la escalera es I/O+CPU; no matar la
  caja). Medir y registrar files/s reales por lote → métricas T9.
- Progreso visible: escribir estado en `.sdd/state/runner.json` (nº done,
  fallos, ESCALAR count) que la UI (T5) puede leer.

## Criterios de aceptación
- Test: lote de 5 fixtures reales de tests/fixtures/ end-to-end ⇒ outcomes
  válidos + re-run idéntico byte a byte y 0 re-procesos.
- Test: crash simulado a mitad ⇒ reanudación completa sin duplicados.
- Test: archivo con timeout ⇒ ESCALAR + batch continúa.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.

---

## Resolución (W2 — 2026-09-19)

Implementado `src/albertitos/run.py` (módulo ejecutable `python -m
albertitos.run`) + `tests/test_run.py` (11 tests).

Decisiones documentadas:
- **Orden determinista**: enums `file_id` ascendente; la EXTRACCIÓN puede ir
  en paralelo (≤2 en vuelo) pero la DECISIÓN se toma siempre en el hilo
  principal, en orden — así el NO_DOUBLE_PAYMENT y el output son idénticos
  entre ejecuciones, con o sin concurrencia.
- **Rung 4 serializado**: health-check a `llama-server` (`/v1/models`, 2 s).
  UP ⇒ workers=1 (todo el lote secuencial: el rung 4 nunca corre en paralelo
  con el resto, 8 cores compartidos). DOWN ⇒ workers≤2 y el rung 4 se salta
  por su propio health-check (`skipped:llama-server-not-running`), el lote
  sigue degradado, nunca parado. `use_rung4=False` desactiva de forma
  determinista (tests: rechazo de conexión inmediato, sin billing).
- **Timeout por archivo**: presupuesto medido desde la ENTRADA EN COLA
  (procesando o esperando slot tras un colgado). Timeout ⇒ decisión ESCALAR
  con veredicto `RUNNER_TIMEOUT:UNKNOWN`, evidencia (stage=decision,
  outcome=ESCALAR, detail=timeout) y el lote sigue. El timeout NO se cachea
  como definitivo: re-run sin colgado re-evalúa el ítem con normalidad.
- **Reanudación**: idempotencia por fila de decisión del file_id (coherente
  con T4: el cache-hit exige fila en store). Crash simulado en el ítem N ⇒
  re-run completa el lote sin duplicados (test).
- **Concurrencia**: máximo 2 en vuelo (cap duro en `max_in_flight`).
- **Métricas**: files/s real del lote (medido) en `.sdd/state/runner.json`
  (total/done/pendientes/fallos/timeouts/resultados/concurrency/rung4/
  timeout_s/engine_version/config_version) para la UI (T5); todo etiquetado
  como medido (§9). Ledger y evidencia en `.sdd/` (jamás /tmp).
- **Emisión + validador**: `emit_outcomes` (T4) + `validate.validar` (T9).
  El CLI omite la validación con `--limit/--only` (lote parcial) y la ejecuta
  en lote completo; exit 0/1 según el validador.
- CLI: `--facturas --outcomes --store-root --rules --maestro
  --fecha-referencia --limit --only --timeout --max-in-flight`. Los defaults
  apuntan al corpus real (`caja-de-alberto/facturas`, solo lectura; el
  maestro se lee, jamás se escribe).
- Smoke real verificado: 1 factura fantasma (FA-2508) end-to-end con el
  maestro real ⇒ ESCALAR, rung 4 UP detectado, resumen con files/s medido.
