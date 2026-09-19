# T40F3 · pypdfium2 NO es thread-safe: extracción concurrente ⇒ SEGV del proceso
assignee: W5
priority: p1
severidad: p0 (el crash mata el proceso entero: runner 24/7, suite, drills)

## Hallazgo (repro real, stack capturado hoy)
`run.py` extrae con 2 workers cuando el rung 4 está CAÍDO
(`max_workers(): 1 si rung4_disponible else min(2, max_in_flight)`) — es
decir, justo en la degradación que ejercita el drill. Dos hilos llamaban
SIMULTÁNEAMENTE al C de pdfium (`PdfDocument`, `get_page`, `render`,
`close`) en `ladder.extract_page` (pypdfium2 no añade locks) ⇒ **SIGSEGV**:

```
Fatal Python error: Segmentation fault
  pypdfium2/_helpers/document.py:400 in get_page
  src/albertitos/extract/ladder.py:148 in extract_page   (hilo 1 y hilo 2)
  src/albertitos/run.py:282 in _extract (ThreadPoolExecutor)
```

Nondeterminístico: los tests del drill fallaban unas corridas sí y otras no
(comprobad en la suite completa de hoy). En el runner 24/7, un SEGV mata el
proceso completo — no hay evidence row de un proceso muerto.

## Fix (la causa)
Lock global `_PDFIUM_LOCK` alrededor de TODA entrada al C de pdfium en
`ladder.py` (crear documento, `pdfium_doc[i]`, render en `_ensure_png` y en
`ctx2`, `close`). El raster se serializa; los rungs 3–5 (tesseract en
subproceso, VLM por HTTP, red) siguen en paralelo. Referencia: la FAQ de
pypdfium2 exige un lock (o procesos) cuando hay hilos.

## Test de regresión
`tests/test_concurrencia_extract.py`: extracción con 4 hilos solapados
(3 rondas, cache fresca por ronda para forzar renders) debe producir LO
MISMO que la corrida serial (rungs, page_sha, evidencia por etapa). Sin el
lock este test crashea el proceso con probabilidad alta; con el lock es
determinista.

## Coste/riesgo/beneficio
~8 líneas en src/ + test. Riesgo: el raster se serializa entre workers
(con rung 4 UP ya era secuencial — `max_workers()==1`; cuando cae, la
concurrencia que queda es I/O, no raster). Tras el cambio: validador
500/500 + pytest + ruff en verde.