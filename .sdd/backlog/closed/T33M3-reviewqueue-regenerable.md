# T33-M3 · Cola de revisión: dedupe O(1) amortizado + regenerador
assignee: W1
priority: p2

## Objetivo
Dos pequeños del mismo módulo (cola de revisión, mi T7):
1. `ReviewQueue.enqueue` relee el fichero completo en cada llamada (O(n) por
   enqueue ⇒ O(n²) por lote a medida que crece). Cache perezoso de
   page_sha256 ya vistos por instancia: se lee UNA vez, el disco sigue siendo
   la fuente de verdad al reconstruir.
2. La cola es estado DERIVADO (se reconstruye desde las caches de página, sin
   re-facturar cloud) pero no había comando para regenerarla — y de hecho se
   perdió en una corrida del suite (ver SUGERENCIAS #1). Se añade
   `tools/regen_review_queue.py` idempotente.

## Cambio
- `ReviewQueue._seen` perezoso + `_seen_page_shas()`; enqueue añade al set.
- `tools/regen_review_queue.py` (regenera con `invoice_uuid` correcto).
- Test: 3 enqueues ⇒ la cola se lee UNA vez y quedan 3 pendientes.

## Test
test_rung5_cloud.py::TestReviewQueueDedupeCache + regeneración real ejecutada
(29 páginas, cache replay, 0 llamadas nuevas).