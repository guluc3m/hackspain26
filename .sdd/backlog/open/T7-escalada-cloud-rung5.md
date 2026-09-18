# T7 · Rung 5: escalada a VLM cloud + cola de revisión (no bloqueante)
assignee: W1
priority: p1

## Objetivo
Cablear el rung 5 de la escalera (AGENTS.md §3 y §13): cuando tesseract Y el
VLM local quedan por debajo de umbral, la página escala a un modelo cloud
>25B multimodal, y el ítem entra en la cola de revisión humana SIN bloquear el
lote. Continúa naturalmente tu trabajo de T1 (`src/albertitos/extract/`).

## Requisitos
- Cliente cloud OpenAI-compatible con visión: base_url/model/key SOLO por
  variables de entorno (p.ej. `ALBERTITOS_ESCALATE_BASE_URL`, `_MODEL`,
  `_API_KEY`; el preset de referencia es `claude-opus-4-5` → Qwen3.8-27B-Vision,
  >25B multimodal). NADA hardcodeado (AGENTS.md §13 higiene de secretos).
- La lectura del cloud es UN CANDIDATO MÁS (`extraction_method: "cloud_vlm"`)
  en el campo — jamás respuesta automática. El resultado PAGAR/NO_PAGAR/ESCALAR
  lo sigue decidiendo solo el motor de reglas.
- temp 0, determinismo: la misma página produce la misma petición (hash de
  prompt en evidencia). Cache (page_sha256, engine=cloud_vlm, engine_version,
  config_version) — reintentar NUNCA re-factura una llamada.
- Timeout + reintento con backoff ante 429/5xx (usa `Retry-After`); si el
  proveedor falla, la página queda ESCALAR en la cola de revisión con lo que ya
  hay — el batch sigue. Degradar, no abortar.
- Cola de revisión: escribe el ítem con imagen de página (png del raster) y
  todas las lecturas candidatas lado a lado en `.sdd/review-queue/` (formato
  acordado con W3: lee `src/albertitos/ui/ledger.py` en worker/w3 para el
  esquema que la UI ya consume) + provenance (quién, cuándo, qué modelo).
- El override humano (si llega) alimenta SOLO la extracción; la decisión se
  recalcula de forma determinista. La UI ya encola overrides en
  `.sdd/review-queue/` — respétalo y no dupliques el mecanismo.

## Criterios de aceptación
- Test con servidor mock (httpx MockTransport): candidato añadido al campo,
  evidencia escrita, cache evita la 2ª llamada, 429 ⇒ backoff y degradación a
  ESCALAR sin abortar.
- Test: el rung 5 jamás emite un result — solo candidatos.
- `uv run pytest` y `uv run ruff check .` en verde; ticket a closed en el mismo commit.
