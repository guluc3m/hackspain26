<<<<<<< HEAD
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
=======
# SUGERENCIAS.md — mejoras pendientes (apéndice colectivo, T33)

Apéndice colectivo: cada worker AÑADE entradas al final; nunca reescribe las
de otros. Formato: título + categoría · problema con evidencia citada ·
propuesta y coste · por qué NO se implementó ya · prioridad y responsable.

---


## · Drill en vivo: carrera de timing bajo carga (flake medido) — W2

- **Categoría**: operación.
- **Problema**: `test_drill_stub_kill_degrada_y_recupera_outcomes_identicos`
  (tests/test_drill_rung4_live.py) falla ~1 de cada 3 suites completas con
  `archivos_con_rung4_skip == 0` y pasa siempre en solitario. Causa probable:
  el watchdog del drill (`drill_rung4_live.py::_watchdog`, poll 0.25 s) y el
  delay del stub (0.8 s) son de la misma magnitud que la latencia de
  scheduling bajo carga — el kill puede aterrizar justo después de que el
  handler del stub ya respondió, sin degradar ninguna página.
- **Propuesta**: (a) subir el delay del stub en el test a 1.5–2 s; (b) bajar
  el poll del watchdog a 0.1 s; (c) volver a intentar la condición del kill
  hasta 2 veces si 0 páginas degradaron (assert con reintento). ~20 líneas,
  solo tests/DrillConfig.
- **Por qué NO se implementó ya**: es higiene de un test mío (no una mejora
  de producto); el ciclo T33 limita a 3 mejoras implementadas y este turno
  agotó las mías (M2/M3/M4). Prioridad baja: el drill EN VIVO real (T24,
  evidencia del guion) no usa el stub.
- **Prioridad**: media. Quién: W2.


## · Circuito (circuit breaker) global del rung 4 — W2

- **Categoría**: arquitectura.
- **Problema**: durante una degradación, CADA página del rung 4 sondea
  health por separado (`rungs.py::_vlm_probe`, llamado desde `run_vlm` por
  página). En el drill real (T24, `.sdd/metrics/drill-rung4-live.json`)
  fueron 12 sondas + reintentos en 30 s de servidor caído. Un circuito
  compartido (tras N fallos consecutivos, saltar la sonda durante un período
  conocido y re-probar una vez por período) ahorraría el sondeo por página
  y aceleraría la degradación.
- **Propuesta**: singleton de estado en `ExtractionLadder` (no global de
  proceso) con estados closed/open/half-open y ventanas configurables en
  `ExtractionConfig` (circuit_threshold, circuit_cooldown_s). ~80 líneas +
  tests con stub.
- **Por qué NO se implementó ya**: cambia la semántica de cuándo se
  intenta el rung 4 (no la decisión, pero sí la escalera); requiere ADR
  (AGENTS.md §4/§12) y un drill determinista que demuestre que el circuito
  se re-cierra solo. Riesgo de enmascarar un server que recupera lento.
- **Prioridad**: alta. Quién: W2 con supervisor (ADR).


## · Batch del rung 4: múltiples páginas por request de VLM — W2

- **Categoría**: extracción.
- **Problema**: el rung 4 mide ~8 s/página en el drill en vivo (llama-server
  CPU, 1 en vuelo por doctrina); una factura de 3 páginas escaneadas ⇒ ~24 s
  solo en rung 4. El server acepta cola pero serializa.
- **Propuesta**: agrupar las páginas de UN archivo en un solo request
  multimodal (varias image_url en el mismo chat) o arrancar un slot paralelo
  de llama-server (`-np 2`) con presupuesto de RAM medido (2.8 GB → ~5.6 GB,
  cabe en 12 GB medidos). ~150 líneas (ladder pasa de per-page a per-batch
  para rung 4; cache por página se mantiene).
- **Por qué NO se implementó ya**: toca la escalera (T1, W1) y el
  presupuesto de threads compartidos con la flota; `--no-warmup`/-np cambia
  el perfil de RAM medido en el T23 (perfil de carga). Requiere medir
  latencia p95 antes/después con el corpus.
- **Prioridad**: media-alta. Quién: W2 (con W1 por el cache de páginas).


## · QR del rung 2: candidatos estructurados (Facturae/Faktura) — W2

- **Categoría**: extracción.
- **Problema**: `rungs.py::run_raster_qr` guarda el payload del QR como
  string crudo (`qr_payload`); el corpus midió 0 páginas solo-QR
  (`.sdd/metrics/corpus-dryrun.json::rutas`), así que el parser no tiene
  extractor para el formato portugués/veri-factu.
- **Propuesta**: extractor `qr-structured` en `parse/extractors.py` que
  mapee los campos del payload (fecha, total, NIF emisor) a candidatos con
  feature_ref. ~60 líneas + fixture sintético de QR (pypdfium2 puede
  rasterizar un QR sintético para el test).
- **Por qué NO se implementó ya**: sin corpus real de QR no hay fixture
  representativo; inventar formato es exactamente lo que la doctrina
  prohíbe (AGENTS.md: nunca inventar registros).
- **Prioridad**: baja hasta que el lote 2 (o el usuario) traiga QRs reales.


## · Cola de revisión priorizada por dinero en riesgo — W3

- **Categoría**: UI.
- **Problema**: la revisión (T5) muestra los escalados por file_id; el T30
  de W3 ya calcula dinero en riesgo para el resumen, pero la pantalla
  Revisión no ordena por importe ni muestra «cubres el X % del dinero
  revisando estas N».
- **Propuesta**: en `ui/ledger.py` + plantilla `revision.html`, ordenar la
  cola por importe (maestro) descendente y añadir la franja «X % del dinero
  en juego cubierto» del T30. ~80 líneas.
- **Por qué NO se implementó ya**: la UI es de W3 y depende de la telemetría
  del T31; tocar plantillas de otro worker en el loop viola el reparto.
- **Prioridad**: alta. Quién: W3 (con los datos del T30).


## · Ledger: snapshot de state/runner.json como evento append-only — W2

- **Categoría**: operación.
- **Problema**: el throughput/fps de cada corrida solo vive en el ÚLTIMO
  `state/runner.json` (se sobreescribe); el histórico de throughput por
  corrida se pierde (el guion T20 y la pantalla Operaciones lo citan como
  «medido» pero solo existe la última medición).
- **Propuesta**: evento `{"event": "run-summary", ...}` en el ledger al
  final de cada `Runner.run()` (elapsed, files_per_second, resultados). El
  ledger es append-only y los eventos existentes (decision/resolution) no
  cambian de formato. ~25 líneas en run.py + lectura en metrics.py.
- **Por qué NO se implementó ya**: el formato del ledger es contrato de
  T4/T9 y el validador de métricas (T9) lee por tipos de evento; añadir un
  tipo nuevo es seguro pero conviene hacerlo cuando W3 refresque la
  explotación del ledger (T31 telemetría).
- **Prioridad**: media. Quién: W2 (store/ledger es mío).


## · Presentación: capítulos y regeneración post-lote — W2

- **Categoría**: producto.
- **Problema**: el mp4 (T32) no tiene capítulos/índice para saltar a la
  sección en la defensa, y tras el lote 2 las cifras quedarán viejas si no
  se regenera.
- **Propuesta**: (a) inyectar capítulos del mp4 (ffmpeg metadata con los
  inicios de cada sección — ya calculados en `Root.tsx::DUR`); (b) añadir al
  `scripts/stage_delivery.sh` un paso opcional que regenere datos + render si
  hay cambios en .sdd/metrics (hash del JSON). ~40 líneas.
- **Por qué NO se implementó ya**: depende de ffmpeg (no en PATH sin
  user-space extra) y el mp4 de la defensa es un entregable ajeno al repo;
  además el render ya está verificado y no quiero re-renderizar antes de la
  entrega sin necesidad.
- **Prioridad**: baja. Quién: W2 (con Alberto decidiendo si entra en la defensa).
>>>>>>> worker/w2

---

## · Panel «Trabajo pendiente» en Salud (trazabilidad, 20 pts) — W2

- **Categoría**: trazabilidad / observabilidad.
- **Problema**: la rúbrica pide mostrar «estado, evidencia, versiones, latencia,
  errores, reintentos y TRABAJO PENDIENTE» (hackathon.maisa.ai, 20 pts). Hoy la
  evidencia registra ese trabajo disperso: los reintentos de health del rung 4
  (stage `extract:rung4_health`, outcome `retry`, T33-M4), los skips
  transitorios de proveedor (`outcome='skipped'` con detail
  `skipped:llama-server-{loading,hung}` — por definición de T29 NO se cachean,
  así que son trabajo que queda por hacer), la cola de revisión (n entradas) y
  los timeouts de runner. Salud los muestra parcialmente y dispersos; no existe
  una cifra única de «esto es lo que queda».
- **Propuesta**: tarjeta «Trabajo pendiente» en Salud con 4 contadores medidos
  de la evidencia real: (a) páginas con skip transitorio no resuelto, (b)
  reintentos de health de la última corrida, (c) escalados en cola de revisión,
  (d) timeouts del runner. Cada contador enlaza a su pantalla (Revisión, runner
  state). ~60 líneas en `ui/ledger.py` + `salud.html` (W3) + un test con ledger
  sembrado. Es puro aggregation sobre evidencia existente: cero cambios de
  decisión y cache.
- **Por qué NO se implementó ya**: la pantalla Salud es de W3 y su telemetría
  está en curso (T31); el ciclo de implementación de W2 ya tenía 3 mejoras.
- **Prioridad**: alta (rúbrica 20 pts, barato). Quién: W3 con W2 (la agregación
  de evidencia es del store, mío).

## · Exportador de asientos al ERP: cerrar la costura de verdad (bonus +10) — W2

- **Categoría**: producto.
- **Problema**: la norma dice «NUNCA pagar sin cruzar con el ERP» y el manual
  del bridge de 2009 (caja-de-alberto/MANUAL_ERP_2009.md) soporta cargar un
  export: `python3 alberto_erp.py --lote2 ruta/al/erp_export_lote2.csv`. Hoy
  la costura ERP es de LECTURA (ORDER_PENDING consulta el estado); no existe el
  camino de VUELTA: los PAGAR del lote tendrían que teclearse a mano en el ERP
  — exactamente el trabajo que el sistema debe ahorrar a Alberto (bonus: mejora
  original implementada, no maqueta).
- **Propuesta**: `python -m albertitos.erp_export` — lee del store los PAGAR
  validados (result + reglas + evidencia) y produce `erp_export_lote2.csv` en
  el formato que `alberto_erp.py` ingiere (leyendo su parser en
  caja-de-alberto/, SOLO LECTURA), con columnas de trazabilidad opcionales.
  Idempotente por (file_id, sha256): re-ejecutar no duplica asientos. ~100
  líneas + test contra el formato real del parser del ERP.
- **Por qué NO se implementó ya**: el ERP es fuera de scope salvo la costura y
  este cambio produce un ENTREGABLE de producto nuevo — hay que aprobarlo con
  el supervisor y con Alberto (¿el CSV entra como asiento pendiente o como
  pagado?). Requiere leer el formato exacto del parser del bridge.
- **Prioridad**: alta como CANDIDATO DE BONUS (+10 máx, desempate 3º). Quién:
  W2 con supervisor.

## · Ingesta de NUEVOS TIPOS de archivo: email .eml con adjuntos — W2

- **Categoría**: escalabilidad.
- **Problema**: la rúbrica (25 pts) exige «plan para incorporar más volumen y
  NUEVOS TIPOS de archivo». El plan existe a nivel de discurso (parser
  extensible, motor de reglas data-driven), pero no hay ni un tipo no-PDF
  demostrado. La pieza barata y honesta: email .eml (el flujo real de Alberto:
  facturas llegan por correo) → `ExtractionFeature` de texto del cuerpo + los
  adjuntos PDF van DIRECTOS a la escalera existente por página.
- **Propuesta**: `extract/email.py` — `ExtractionFeature(type="email_text")`
  con remitente/asunto/cuerpo (stdin o rutas) + reenvío de los adjuntos
  application/pdf a `ladder.extract_file`. El parser ya ignora tipos que no
  sabe y el motor no cambia. Sin QR ni OCR nuevos. ~80 líneas + fixture .eml
  sintética con adjunto de los fixtures reales (nada inventado).
- **Por qué NO se implementó ya**: el reto solo trae PDFs; sin corpus de
  emails real no hay fixture representativa (misma doctrina que la sugerencia
  del QR estructurado). Como PLAN para la defensa puntúa (25 pts) aunque se
  demuestre con fixture sintética etiquetada como tal.
- **Prioridad**: media (25 pts de rúbrica). Quién: W2 (extract es mío/W1).
