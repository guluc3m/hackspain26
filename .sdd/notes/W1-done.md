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
  claude-opus-4-5 → Qwen3.8-27B-Vision), prompt fijo + temp 0 (hash de prompt
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
