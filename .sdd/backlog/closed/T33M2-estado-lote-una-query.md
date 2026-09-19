# T33-M2 · Estado del lote para la UI en UNA query (era O(N²))
assignee: W2
priority: p2

## Objetivo
`Runner._write_state` (src/albertitos/run.py) consulta `store.decision_for()`
por archivo en cada tick (tick por archivo) ⇒ O(N²) SELECTs en un lote de 500
(≈125k queries, medido en el código: `for path in files: decision_for(path)`).
Pasa a UNA query por tick sin cambiar el JSON de estado que consume la UI T5.

## Cambio
- `store.py::resultados_por_file(file_ids)` — un `SELECT file_id, result
  FROM invoices WHERE file_id IN (...)` (chunks de 500).
- `_write_state` usa ese mapa; el JSON de `state/runner.json` queda
  byte-idéntico (misma lógica de conteo y claves).

## Test
`tests/test_loop_m2.py`: (a) resultados_por_file devuelve el mapa correcto
con file_ids sembrados y devuelve {} con lista vacía; (b) el JSON del estado
tras un mini-lote es idéntico antes/después del cambio (regresión de formato).
