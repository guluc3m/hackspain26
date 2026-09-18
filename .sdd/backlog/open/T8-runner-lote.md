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
