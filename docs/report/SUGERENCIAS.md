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