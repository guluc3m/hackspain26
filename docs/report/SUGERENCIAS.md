# SUGERENCIAS — apéndice colectivo (workers ociosos → ideas grandes)

Cada worker AÑADE entradas (nunca reescribe las de otros). Formato: título,
categoría, problema con evidencia citada, propuesta + coste, por qué no se
implementó ya, prioridad y responsable sugerido. Lo pequeño y seguro se
implementa con ticket propio; lo grande/riesgoso vive aquí.

---

## 1. [operación] El simulacro del lote 2 borra la cola de revisión real
- **Problema**: `tests/test_simulacro.py` (T21, W2) ejecuta
  `shutil.rmtree(Path(".sdd/review-queue"), ignore_errors=True)` (líneas 138 y
  165) sobre el directorio REAL compartido, no sobre un sandbox. Medido en
  este worktree: tras cualquier `pytest` completa, `review.jsonl` (29 páginas
  escaladas con imagen + candidatas, evidencia del T7/T22) desaparece y los
  tests `test_defensa` y `test_ui_lote1` quedan rojos — la fuente citada por
  DEFENSA.md `.sdd/lote1/review-queue/review.jsonl` deja de existir.
- **Propuesta**: que el simulacro use su propio `store_root` sandbox (como ya
  hace el drill T24: `DRILL_TMP`) — el rmtree debe apuntar al sandbox, no a
  `.sdd/review-queue`. Un cambio de ~2 líneas.
- **Por qué NO ya**: es un archivo de otro worker (regla dura de no tocar);
  lo comunica W1 al supervisor vía este apéndice.
- **Coste**: ~2 líneas + re-run. **Riesgo**: nulo (el simulacro ya usa
  sandbox para el resto del estado).
- **Prioridad**: ALTA — bloquea suite verde entre workers. **Quién**: W2.

## 2. [operación] Puerto fijo 8231 del stub de rung 4 ⇒ colisión entre workers
- **Problema**: `tests/test_drill_rung4_live.py` usa `STUB_PORT = 8231` fijo.
  Observado hoy: dos `pytest` concurrentes (fleet/w2 y hackspain26) ⇒
  `OSError: [Errno 98] Address already in use` y fallos transitorios del drill.
- **Propuesta**: puerto desde env con fallback (`int(os.environ.get("ALBERTITOS_STUB_PORT", "8231"))`)
  o puerto efímero (`socket.bind(("127.0.0.1", 0))` + descubrir el elegido).
- **Por qué NO**: es archivo de otro worker; el fallo es transitorio y difícil
  de reproducir en solitario.
- **Coste**: ~5 líneas. **Prioridad**: ALTA (falsos rojos entre workers).
  **Quién**: W2 (dueño del drill).

## 3. [arquitectura] Cola de trabajo persistente con leasing para lote 2
- **Problema**: el runner paraleliza con `ThreadPoolExecutor` in-process
  (src/albertitos/run.py) y reparte timeouts por presupuesto de cola. Con dos
  workers concurrentes sobre el MISMO store (como exige el lote 2: 40 facturas
  + reprocesado), no hay leasing: dos procesos pueden decidir el mismo
  file_id a la vez y duplicar llamadas rung 4/5 (el cache de página amortiza,
  pero el presupuesto de timeout y el orden determinista se rompen).
- **Propuesta**: tabla `work_queue` en el store (sha, estado, lease_until,
  worker_id) con claim atómico (`UPDATE ... WHERE estado='pendiente'`) — el
  runner actual consume de la cola. ~150 líneas + tests de concurrencia.
- **Por qué NO**: no hubo necesidad real aún (lote 1 = 1 runner); el lote 2
  (sábado) es el momento de medir si hace falta de verdad.
- **Coste**: ~150 líneas + tests. **Riesgo**: medio (toca el orquestador, no
  el motor). **Prioridad**: media. **Quién**: supervisor decide + W2.

## 4. [extracción] A/B: textpage de pypdfium2 como rung 1 alternativo
- **Problema**: el rung 1 usa `pypdf` (`.sdd/metrics/corpus-dryrun.json`:
  29 páginas sin capa de texto usable). pypdfium2 tiene `PdfTextPage` con un
  extractor de texto distinto que a veces recupera texto donde pypdf devuelve
  mojibake o vacío (fuentes CID mal mapeadas). Si recuperara algunas de las
  29, bajaría el coste de rung 4 (9 invocaciones × ~16 s medidos en T14).
- **Propuesta**: añadir un rung 1b (pypdfium2 textpage) ENTRE rung 1 y rung 2,
  con la MISMA puerta de plausibilidad, como candidato `pdf_text` con
  `extraction_method: "pypdfium2"`. A/B medido sobre las 29 páginas del
  dry-run (cache ya lo permite); solo se activa si gana.
- **Coste**: ~40 líneas + corrida A/B. **Por qué NO**: cambia la escalera
  (requiere re-dry-run para no invalidar la calibración) y la ganancia es
  desconocida sin medir. **Prioridad**: media. **Quién**: W1.

## 5. [extracción] A/B de tessdata_best para los 14 NO_PAGAR genuinos
- **Problema**: la calibración T10 midió con `tessdata_fast` (conf. media 56,7
  en las 29 páginas OCR, 14 NO_PAGAR genuinos por importe). `tessdata_best`
  puede subir word-conf y cobertura y resolver algunas genuinas sin pasar por
  el VLM (ahorro ~16 s/página medido).
- **Propuesta**: repetir la calibración (`tools/calibrate_rung3.py`, ya
  parametrizable) con `tessdata_best` y comparar las distribuciones; si el
  hueco bimodal se ensancha, recalibrar umbrales (ADR, es config).
- **Coste**: ~30 MB de datos + 1 corrida del script. **Por qué NO**: el
  binario tesseract no está en PATH (se midió con tesserocr); requiere
  decisión de si el rung 3 entra en producción con datos best (más lento:
  ~2× latencia según documentación de tessdata).
- **Prioridad**: media. **Quién**: W1 con visto del supervisor.

## 6. [reglas] Umbrales por proveedor como datos del maestro
- **Problema**: `outlier_total` y `tolerancia_importe` son globales
  (`regla_v3.yaml`). El outlier 84700 (PO-2026-0497) disparó AMOUNT_OUTLIER en
  10 archivos del lote 1 (T14), y proveedores con importes habituales altos
  acabarán en ESCALAR de crónica. La doctrina v3→v4 ya contempla reglas como
  datos.
- **Propuesta**: que el maestro pueda llevar columnas de umbrales por
  proveedor (`tolerancia_pct`, `outlier_cap`) que el motor lea como parámetros
  por-pedido — sigue siendo datos, el motor no cambia (mismo patrón que
  `params_for("REGLA_V4")`).
- **Coste**: ~80 líneas (maestro + 2 reglas) + tests. **Por qué NO**: cambia
  la SEMÁNTICA de reglas activas ⇒ exige supervisor + probablemente lote 2
  para validar contra datos reales. **Prioridad**: alta si el lote 2 trae
  proveedores grandes. **Quién**: supervisor + W2.

## 7. [producto] Resumen de Alberto como servicio periódico
- **Problema**: `resumen_alberto.pdf` (T26, W3) se genera a demanda. Alberto
  necesita el «¿qué pago hoy y por qué?» SIN abrir la UI: hoy hay que correr
  el comando a mano.
- **Propuesta**: cron diario que regenere `resumen_alberto.pdf` + lo deje en
  una carpeta conocida (o correo); reutiliza `albertitos.resumen` y el
  mecanismo cron existente del agente.
- **Coste**: ~20 líneas + 1 entrada de cron. **Por qué NO**: decisión de
  producto del usuario (¿PDF semanal? ¿diario? ¿dónde?); fuera del alcance
  técnico. **Prioridad**: baja (post-reto). **Quién**: usuario + W3.

## 8. [UI] Vista Impacto alimentada por diffs T13 medidos
- **Problema**: la pantalla Impacto (T5) muestra diffs de reprocesado, pero el
  formato de entrada no está normalizado: T18 produjo
  `impacto-fix-colapso.json` y T13 tiene su propio formato `impacto.json` —
  dos schemas para lo mismo.
- **Propuesta**: unificar en `ui/ledger.py` un loader de diffs (kind
  "impacto") que acepte ambos y alimente la pantalla; los futuros reprocesos
  (lote 2) ya nacen con el schema correcto.
- **Coste**: ~60 líneas. **Por qué NO**: es archivo de W3 y el lote 2 define
  el formato definitivo. **Prioridad**: media. **Quién**: W3.

## 9. [operación] Histórico de corridas del runner (runner.json se pisa)
- **Problema**: `.sdd/state/runner.json` se SOBREESCRIBE en cada corrida —
  durante T18 el reproceso (108 archivos, cache caliente) pisó las métricas de
  la corrida completa de T14 (4.162 files/s) y hubo que restaurarlas desde
  git. La serie temporal de throughput/coste no puede comparar corridas.
- **Propuesta**: append a `.sdd/state/corridas.jsonl` (run_id, ts, engine,
  métricas) además del runner.json vigente; la vista Operaciones ya puede
  dibujar la serie.
- **Coste**: ~20 líneas en run.py. **Por qué NO**: toca el runner (W2) y el
  esquema de estado en pleno ciclo de entrega; riesgo bajo pero alcance de W2.
- **Prioridad**: media. **Quién**: W2.