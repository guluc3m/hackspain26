# W1 — resumen de sesión

## Tickets completados
- **T1 · Escalera de extracción (rungs 1–4)** — commit 7dd8b9e en worker/w1.
  Ticket movido a `.sdd/backlog/closed/T1-escalera-extraccion.md`.

## Qué quedó implementado (src/albertitos/extract/)
- `config.py` — ExtractionConfig (todos los umbrales son configuración,
  `config_version` para invalidar cache; valor "extract-v1").
- `plausibility.py` — puerta del rung 1: cobertura de glifos ("(cid:N)",
  U+FFFD, control) + ratio diccionario ES/EN contra mojibake de fuentes CID.
- `raster.py` — render pypdfium2 (dpi configurable), PNG, QR con
  detectAndDecodeMulti + fallback a decodificación simple (cv2 5.x la falla
  en QRs limpios), fracción de píxeles oscuros fuera de los QRs para decidir
  "solo-QR".
- `rungs.py` — los 4 rungs; cada uno devuelve RungOutcome + escribe fila de
  evidencia completa (stage/extractor/versión/hash/latencia/outcome/detalle).
  Nada devuelve strings sueltos.
- `cache.py` + `ladder.py` — cache por página con clave
  (page_sha256, engine, engine_version, config_version) en .sdd/cache/,
  PNG por página en .sdd/cache/images/ (materia prima para rungs 3–5 y la
  cola de revisión); re-ejecutar = cache_hit (no-op, latencia 0).
- `evidence.py` — EvidenceLedger JSONL append-only (por defecto bajo .sdd/).

## Decisiones tomadas (documentadas también en el commit)
1. **page_sha256 = sha256(doc_sha256 + ":" + page_index)** — determinista y
   único por página de documento (el ticket pedía "sha256_pagina").
2. **Rung 2 en cache, rung 1 no** — el rung 1 es determinista y barato; la
   re-renderización y QR sí se cachean para no re-coste en OCR/VLM.
3. **QR-only se decide con umbral de píxeles oscuros fuera de los bboxes**
   (config: qr_only_max_outside_dark_fraction=0.02), no con heurística de
   "texto". Si coexisten QR y contenido ⇒ feature qr_payload + continuar.
4. **Tesseract ausente** se resuelve con `shutil.which` + existencia del
   binario configurado ⇒ `skipped:tesseract-not-on-PATH`; el lote sigue.
5. **Rung 5 (cloud VLM) NO está en T1** — es camino de escalada y su lectura
   es un candidato más; se cablea en parser/revisión (T2/T5) por diseño.
6. **VLM rung 4**: prompt JSON estricto, temp 0, cover de campos esperados
   como confianza; disponible pero `skipped:llama-server-not-running` si el
   sidecar no está.

## Desviaciones del ticket (documentadas)
- Los `scan_*.pdf` reales pesan ~57–61 KB, no <5 KB como estimaba el ticket.
- Se usó `cv2.QRCodeDetector` (opencv ya era dependencia) — sin nueva
  dependencia; `zxing-cpp` no se añadió por no estar en pyproject (justificado
  en el ticket como alternativa; cv2 cubre el caso).
- El worktree tenía un merge en curso de main al empezar; al resolverlo se
  tomó la versión de main para AGENTS.md/.gitignore/T1/T6 (material del reto
  + DECISIONS.md + T6 vía plantilla Typst). La rama quedó alineada con main.

## Estado final
- `uv run pytest` 20/20 verde; `uv run ruff check .` limpio.
- Higiene de secretos: sin apiKey/sk- en src/tests/.sdd.
- Sin push (regla dura). Restante en open: T2/T3/T4 (W2), T5/T6 (W3).

## Actualización 2: T7 · Rung 5 cloud + cola de revisión (commit en worker/w1)
- `src/albertitos/extract/cloud.py`: CloudConfig SOLO por env
  (ALBERTITOS_ESCALATE_BASE_URL/_MODEL/_API_KEY; preset de referencia
  deepseek-v4.1-flash (AGENTS §13: Qwen3.8 vetado)), prompt fijo + temp 0 (hash de prompt
  en evidencia y provenance), retry 429/5xx con Retry-After/backoff (4xx
  permanente falla sin reintentar), httpx con transporte inyectable.
- `run_cloud_vlm`: el candidato cloud entra con extraction_method "cloud_vlm";
  el módulo NO puede emitir PAGAR/NO_PAGAR/ESCALAR (test con AST lo garantiza).
- Cache (page_sha256, cloud_vlm, model, config_version): reintentar jamás
  re-factura (test: 2ª ejecución = 0 llamadas).
- `src/albertitos/extract/review.py`: cola `.sdd/review-queue/review.jsonl`
  con el esquema que la UI de W3 ya consume (kind evidence/fields,
  page_images b64, lecturas lado a lado por extractor, provenance) +
  `read_overrides()` para consumir `overrides.jsonl` SIN duplicar el mecanismo.
- Degradación: proveedor caído ⇒ página queda en la cola con lo que hay,
  el lote sigue; 429 persistente ⇒ outcome error + cola.
- Nueva dependencia: httpx (justificada: MockTransport del ticket + cliente
  HTTP con retry/Retry-After).
- 38 tests verde, ruff limpio.

## Actualización 3: T10 · Dry-run del corpus (500 PDFs) + calibración rung 3
- `src/albertitos/extract/dryrun.py` + CLI (`python -m albertitos.extract.dryrun`):
  idempotente (rung 1 también cacheado ahora; latencias medidas viven en el
  cache y sobreviven al re-run), `--limit`/`--only`, timeout por archivo
  (registrar y seguir), concurrencia capada a 2, métricas en
  `.sdd/metrics/corpus-dryrun.json`, evidencia en
  `.sdd/metrics/evidence-dryrun.jsonl`. No decide resultados (test anti-DECIDE).
- Resultado MEDIDO (500 archivos, 3,57 s, 0 errores): 471 (94,2 %) con capa de
  texto usable; 29 (5,8 %) caen a raster/QR (los 26 sin texto + 3 escaneos
  ilegibles de la doctrina); 0 solo-QR; 493 páginas únicas (duplicados
  detectados). rung 1: 2 636 archivos/s, media 0,4 ms, p95 2,0 ms; rung 2:
  media 42,1 ms, p95 73,0 ms. Suma de rutas cuadra (471+29=500).
- Calibración rung 3 con OCR REAL (tesserocr/libtesseract 5.5.1 user-space,
  NO en pyproject; --no-sync): 29 páginas OCRizadas + 493 capas de texto.
  Distribución bimodal: ilegibles en [17.0, 26.0], legible mínima 42.6.
  Decisión: word_conf 60→40 y cobertura 0.5→0.4 (config extract-v2), con
  porcentajes citados en `.sdd/metrics/calibracion.md` (evidencia ADR D-001):
  89.7% del rung-3 pasa, las 3 debajo son exactamente los ilegibles; 22/29
  (75.9%) se resuelven en rung 3 y 7 escalan al VLM.
- Tests: dry-run reproducible byte a byte (salvo wall), 0 re-procesos,
  rutas cuadradas, fallos sin abortar, workers capados a 2. 105 tests verde.

## Actualización 4: T14 · Corrida real lote 1 → outcomes.jsonl
- Corrida completa (relanzada por el supervisor tras morir el runner; done=500,
  fallos=0, outcomes.jsonl validado con `albertitos.validate`: 500/500).
- Resultados MEDIDOS: 347 PAGAR / 108 NO_PAGAR / 45 ESCALAR; 4.162 files/s
  (120,1 s de pared), rung 4 serializado (llama-server up; 9 invocaciones,
  media 15,8 s, máx 33,7 s), rung 5: 9 invocaciones (5× status-404 del
  proveedor, 5 sin credenciales aún) ⇒ coste cloud facturado 0,00 €.
- `.sdd/metrics/lote1.json` (generado con tools/lote1_metrics.py desde
  store/ledger/runner.json) + triage documentado en
  `.sdd/metrics/triage-revision.md`: 45 ESCALAR por motivo dominante —
  RUNNER_TIMEOUT 20 (timeout 20 s/archivo, hallazgo de seguimiento), mixto 14,
  instrucciones embebidas 5, fecha 3, pedido en revisión 2, IBAN 1. Las 10
  páginas de extracción del rung 5 están dentro de los 45; review.jsonl lleva
  imagen + candidatas para las 10. Nada decidido: humano decide (§6/§7).
- NOTA límite del ticket (runner final): los escaneos con timeout quedaron
  ESCALAR — correcto según política (ante duda, ESCALAR), y re-procesable
  barato vía cache cuando se revise el timeout o llegue lote 2.

## Actualización 5: T17 · Auditoría de trampas contra el outcomes real
- `tools/audit_trampas.py` + snapshot `.sdd/metrics/outcomes-lote1.jsonl`
  (copia del outcomes.jsonl validado, 500) → `.sdd/metrics/auditoria-trampas.md`.
- VERDE: fantasmas (3, ESCALAR citando PROVEEDOR_FANTASMA); FA-8801 duplicado
  (1ª PAGAR, 2ª NO_PAGAR por NO_DOUBLE_PAYMENT — coherente §6); instrucciones
  embebidas (9 marcadas, 0 PAGAR — los datos nunca son comandos); outlier 84700
  ESCALAR; pendiente_revisar PO-2026-0007/0141 ESCALAR; 26/26 scans ESCALAR con
  rung-4 below-threshold (0 confianzas sospechosas). Pedidos 0538–0557 (NIF
  vacío): 0 muestras en lote 1 — riesgo documentado para lote 2.
- **ROJO mayor (hallazgo)**: el motor colapsa values[] con el PRIMER candidato
  de total; cuando la factura trae «Subtotal» + «TOTAL A PAGAR», elige el
  Subtotal y compara contra el importe CON IVA del maestro ⇒ 87 de los 108
  NO_PAGAR son FALSOS (un candidato de total sí matchea con tolerancia 0,01;
  14 genuinos; los otros 7 NO_PAGAR vienen de otros códigos, misma causa
  probable). Bug de matching/selección de candidato (T3/W2), no de extracción
  ni de política — el candidato correcto ESTÁ en el store. Corrección sugerida:
  preferir la línea «TOTAL A PAGAR» o tratar el desacuerdo entre candidatos
  como ambigüedad (ESCALAR, §6), registrando el porqué (AGENTS §2).
- NO se cambian resultados a mano (regla del ticket): ROJO documentado y el
  estado PINNADO en tests/test_auditoria_trampas.py — al corregir y reprocesar
  el test fallará a propósito y forzará re-auditar. El supervisor decide.
- 164 tests verde, ruff limpio.

## Actualización 4: T14 · Corrida real del lote 1 → outcomes.jsonl
- `python -m albertitos.run` sobre los 500 PDFs reales (llama-server UP ⇒ lote
  SECUENCIAL), regla v3, umbrales calibrados T10 (extract-v2), rung 4
  PaddleOCR-VL y rung 5 deepseek-v4.1-flash (credenciales SOLO por env).
- Resultados: PAGAR 347 · NO_PAGAR 108 · ESCALAR 45. Validador OK 500/500.
- 29 ESCALAR = extracción sin resolver (sin capa de texto, tesseract binario
  ausente ⇒ rung 3 skipped; candidatas VLM + deepseek en cola de revisión).
  16 ESCALAR = anomalías de reglas (instrucciones embebidas 9, fecha futura 3,
  pedido en revisión 2, maestro fantasma/IBAN 4...).
- Incidencia documentada y corregida: la primera pasada marcó 20 scans como
  ESCALAR/RUNNER_TIMEOUT (presupuesto desde cola de 120 s detrás de llamadas
  VLM compartidas). Exactitud > velocidad: decisiones timeout borradas del
  store (ledger conserva el histórico) y re-procesadas con --timeout 900 ⇒
  0 timeouts. Re-run posterior: 500/500 reutilizados y outcomes.jsonl
  BYTE-A-BYTE idéntico (verificado con diff).
- Métricas: .sdd/metrics/lote1.json (files/s, latencias por rung — rung 4
  media 28,2 s por página en máquina compartida, rung 5: 25 llamadas cloud ⇒
  ~0,10 € estimado a 0,004 €/llamada (T9), uso de rutas, motivos ESCALAR).
- Drills de resiliencia (T12): 4/4 PASS (provider caído, backoff 429, crash +
  reanudación, ledger corrupto).
- outcomes.jsonl se commitea en la solución (regla dura del ticket); el repo
  de entrega lo prepara el supervisor. Cola de revisión (37 MB con imágenes)
  queda como estado .sdd NO commiteado — regenerable desde cache/store.
