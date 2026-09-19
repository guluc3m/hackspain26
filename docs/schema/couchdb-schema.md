# CouchDB schema — artefactos de la arquitectura

Mapeo de los artefactos definidos en `docs/report/architecture.typ` (y
implementados en `src/albertitos/types.py` + `store/db.py`) a documentos
CouchDB. El documento escaneado y sus metadatos viven como documento +
attachments.

Convenciones globales:

- `timestamp` = Unix epoch seconds (`float`), igual que `types.now()`.
- `_id` **determinista** donde se necesita idempotencia → `PUT` una vez;
  `409 Conflict` = trabajo ya hecho, reuso (equivalente a `INSERT OR IGNORE`).
- Binarios (PDF original, renders de página, crops QR) = **attachments
  standalone**, nunca base64 inline en el JSON.
- Todo documento lleva `type` (para `validate_doc_update` y Mango) y
  `schema_version` (arranca en 1).

## 1 · Bases de datos

| DB | Artefacto de la arquitectura | Ciclo de vida |
|---|---|---|
| `documents` | Fichero escaneado + metadatos + invoice record | mutable solo en `status`/refs; attachments estables |
| `features` | `ExtractionFeature` + caché de escalones (§3) | inmutable por clave de caché |
| `fields` | `ExtractionField` con TODOS los candidatos (Parser) | `values[]` solo-append |
| `evidence` | Fila de evidencia §5 `(invoice_id, stage, …)` | append-only, thin |
| `decisions` | `Decision` (motor de reglas §4) | inmutable (nunca se actualiza) |
| `overrides` | `Override` humano con procedencia (§7) | inmutable |
| `system` | `Run` (mutable) + `ConfigSnapshot` (inmutable) | mixto |

Ledger (§5): el feed `_changes?include_docs=true` de cada DB es el registro
append-only; se puede volcar a JSONL continuamente filtrando por `_doc_ids`.

```
documents (UUID interno, original + pages/* attachments)
   │ 1:N
   ├─ evidence ──feature_ref──▶ features  (caché compartida entre facturas)
   ├─ fields   (1 doc por campo; values[] append-only)
   ├─ decisions (1 por run; inmutable) ──config_ref──▶ system/configs
   └─ overrides (inmutables) ──▶ decisión recomputada (§7)
system/runs ──▶ config_version
```

## 2 · `documents` — documento escaneado + metadatos

Un documento por fichero de entrada. `_id` = UUID interno estable de la
factura (`file_id` es solo el nombre de entrada, nunca se normaliza).

```json
{
  "_id": "inv_7f3c1a2e8b9d4c0fa1e2d3c4b5a69788",
  "_rev": "3-…",
  "type": "document",
  "schema_version": 1,
  "file_id": "factura_123.pdf",
  "sha256": "9af3…",
  "source_format": "pdf",
  "format_status": "supported",
  "mime": "application/pdf",
  "size_bytes": 184233,
  "pages": 2,
  "parts": null,
  "received_at": 1726742400.12,
  "last_seen_at": 1726742400.12,
  "batch_id": "lote2",
  "status": "ESCALAR",
  "decision_ref": { "db": "decisions", "id": "inv_7f3c…:run_2026-09-19T0800", "rev": "1-…" },
  "extraction_profile": "pdf_ladder"
}
```

- `source_format`: `pdf | csv | xlsx | jpg | png` son *supported*; cualquier
  otro se acepta con `format_status: "tentative"` (el pipeline puede
  forzar `ESCALAR` en tentativos).
- `pages`: número de páginas (`pdf/jpg/png`). Para `csv/xlsx` es `null` y se
  usa `parts`: `[{ "sheet": 0, "name": "Hoja1", "rows": 240 }]`.
- `extraction_profile`: `pdf_ladder` (escalera completa), `image_ladder`
  (jpg/png: sin text-layer, arranca en QR/OCR), `table_ladder`
  (csv/xlsx: parse directo, sin OCR).

### Attachments

```
_attachments: {
  "original":        { "content_type": "application/pdf", "revpos": 1, … },
  "pages/0000.png":  { "content_type": "image/png", … },
  "pages/0001.png":  { … },
  "thumbs/0000.png": { … }
}
```

- `original`: bytes exactos del fichero de entrada (cualquiera de los 5 formatos).
- `pages/*.png`: renders de `pypdfium2` (entrada de los escalones 2–5 y imagen
  de la cola de revisión §7). JPG/PNG: `pages/0000.png` puede ser una copia
  normalizada (EXIF limpio) o omitirse. CSV/XLSX: no hay páginas; opcionalmente
  un render a PDF para la UI de revisión.

### Dedupe por sha256 (patrón alias)

CouchDB solo garantiza unicidad en `_id`, así que el hash tiene un doc alias:

```json
{ "_id": "sha256:9af3…", "type": "sha_alias", "invoice_id": "inv_7f3c…" }
```

`PUT` del alias → `409` si el contenido ya fue ingestado → reusar `invoice_id`.

## 3 · `features` — caché de la escalera de extracción

`_id` = clave de caché del contrato (§3/§5): `feature_type:sha256:engine:engine_version:config_version`,
donde `sha256` es el de la **página** (ladders paginados) o de la **parte**
(hoja/rango de tabla). Determinista ⇒ un re-run 24/7 nunca re-factura una
llamada cloud.

```json
{
  "_id": "page_image:9af3…:pypdfium2:6.0.1:cfg-v17",
  "type": "feature",
  "feature_type": "page_image",
  "extraction_method": "pypdfium2",
  "engine_version": "6.0.1",
  "config_version": "cfg-v17",
  "sha256": "9af3…",
  "page": 0,
  "part": null,
  "outcome": "ok",
  "latency_ms": 412,
  "confidence": 0.93,
  "timestamp": 1726742401.5,
  "data": { "width": 1240, "height": 1754 },
  "data_ref": { "attachment": "payload", "sha256": "…" },
  "untrusted": false
}
```

- `outcome`: `ok | skipped:<reason> | fail` — escalón omitido queda registrado,
  nunca aborta el lote (§3).
- Payload binario/grande → attachment `payload`; texto y payloads QR caben en
  `data` inline. Payloads QR: `untrusted: true` (nunca son instrucciones).
- `confidence` de OCR = media ponderada por longitud + término de cobertura de
  campos (doble umbral del §3).
- `features` es compartida entre facturas (misma página misma caché); la traza
  por factura vive en `evidence`.

## 4 · `fields` — campos interpretados, todos los candidatos

`_id` = `"<invoice_id>:<field_type>"`. Nunca se colapsa `values[]` (contrato §2):
colapsar solo dentro de una regla, registrando el elegido.

```json
{
  "_id": "inv_7f3c…:total",
  "_rev": "4-…",
  "type": "field",
  "schema_version": 1,
  "invoice_id": "inv_7f3c…",
  "field_type": "total",
  "timestamp": 1726742410.0,
  "values": [
    { "extractor": "tesseract", "value": "1210.00",  "confidence": 0.91,
      "feature_ref": "ocr_text:9af3…:tesseract:5.3.0:cfg-v17" },
    { "extractor": "vlm",       "value": "1210.00",  "confidence": 0.97,
      "feature_ref": "ocr_text:9af3…:llama-server:b4610:cfg-v17" },
    { "extractor": "cloud_vlm", "value": "1210.00",  "confidence": 0.95,
      "feature_ref": "ocr_text:9af3…:cloud_vlm:gemini-2.5:cfg-v17" }
  ],
  "overrides_applied": []
}
```

- `feature_ref` = trazabilidad candidato → escalón que lo produjo
  ("Cada campo incluirá la información de la feature desde la que se ha
  extraído").
- Actualización = **append** a `values[]` (nuevo run/extractor). Validado.
- La lectura cloud (escalón 5) entra como un candidato más, nunca respuesta
  automática (§3).

## 5 · `evidence` — registro de etapa por factura (§5)

`_id` = `"<invoice_id>:<stage>:<page>:<sha8>:<extractor_version>:<config_version>"`
→ INSERT-OR-IGNORE. Documento fino: el peso está en `features`.

```json
{
  "_id": "inv_7f3c…:zxing:0:9af3abcd:1.2.0:cfg-v17",
  "type": "evidence",
  "schema_version": 1,
  "invoice_id": "inv_7f3c…",
  "stage": "zxing",
  "page": 0,
  "extractor": "zxing-cpp",
  "extractor_version": "1.2.0",
  "config_version": "cfg-v17",
  "sha256": "9af3…",
  "latency_ms": 38,
  "confidence": 1.0,
  "outcome": "ok",
  "detail": { "qrs_found": 1 },
  "feature_ref": "qr_payload:9af3…:zxing:1.2.0:cfg-v17",
  "timestamp": 1726742402.1
}
```

La vista `evidence/by_invoice` es la traza completa de una factura — la página
"todo lado a lado" de la UI de revisión.

## 6 · `decisions` — inmutables

`_id` = `"<invoice_id>:<run_id>"`. Nunca se actualiza (`validate_doc_update`
rechaza la 2ª revisión). El motor es puro; el store sella `created_at`.

```json
{
  "_id": "inv_7f3c…:run_2026-09-19T0800",
  "type": "decision",
  "schema_version": 1,
  "invoice_id": "inv_7f3c…",
  "file_id": "factura_123.pdf",
  "run_id": "run_2026-09-19T0800",
  "result": "ESCALAR",
  "rule_evaluations": [
    { "code": "TOTALS_MUST_MATCH", "verdict": "PASS", "reason": "1210.00 == 1000.00 + 210.00",
      "consumed": { "total": "1210.00", "iva_amount": "210.00" },
      "chosen_candidates": { "total": "vlm@0.97" } },
    { "code": "NIF_IN_MASTER", "verdict": "FAIL", "reason": "B12345678 not in master",
      "consumed": { "nif": "B12345678" } },
    { "code": "IBAN_MATCHES_MASTER", "verdict": "UNKNOWN", "reason": "iban candidates disagree",
      "consumed": { "iban": ["ES91…", "ES19…"] } }
  ],
  "config_ref": { "db": "system", "id": "cfg-v17" },
  "created_at": 1726742500.0
}
```

- `result` restringido a `PAGAR | NO_PAGAR | ESCALAR` (validado).
- `config_ref` apunta al snapshot inmutable `system/configs` — el snapshot del
  momento queda referenciado, no copiado (decisión ADR-able: inline si se
  prefieren decisiones autocontenidas).
- `chosen_candidates` registra qué candidato colapsó cada regla y por qué.

## 7 · `overrides` — correcciones humanas (§7)

`_id` = UUID nuevo, inmutable.

```json
{
  "_id": "ovr_2f9c…",
  "type": "override",
  "schema_version": 1,
  "invoice_id": "inv_7f3c…",
  "field_type": "total",
  "rung": "vlm",
  "before": { "extractor": "vlm", "value": "1210.00", "confidence": 0.97 },
  "after":  { "value": "1120.00" },
  "who": "alberto@…",
  "reason": "digit transposition",
  "decision_recomputed": "inv_7f3c…:run_2026-09-19T0900",
  "timestamp": 1726743000.0
}
```

Procedencia completa (quién, cuándo, desde qué escalón, before/after). Afecta
solo a la extracción: `decision_recomputed` enlaza la decisión rehecha de
forma determinista.

## 8 · `system` — runs y snapshots de configuración

```json
// type: "run" — mutable (started → finished)
{
  "_id": "run_2026-09-19T0800",
  "type": "run",
  "schema_version": 1,
  "started": 1726742400.0,
  "finished": 1726743000.0,
  "config_version": "cfg-v17",
  "master_sha256": "…",
  "batch": "lote2",
  "counts": { "ok": 40, "escalar": 7, "fail": 1 }
}

// type: "config_snapshot" — inmutable, _id = config_version
{
  "_id": "cfg-v17",
  "type": "config_snapshot",
  "schema_version": 1,
  "rule_set_version": "rules-2026.09",
  "thresholds": { "NIF_IN_MASTER": { "min_confidence": 0.9 } },
  "extractor_versions": { "pypdf": "5.1.0", "tesseract": "5.3.0", "llama-server": "b4610" },
  "supported_formats": { "pdf": "supported", "csv": "supported", "xlsx": "supported",
                          "jpg": "supported", "png": "supported", "heic": "tentative" },
  "master_sha256": "…",
  "created_at": 1726740000.0
}
```

## 9 · `validate_doc_update` — el contrato vive en la BD

```js
// decisions / overrides / system (config_snapshot): append-only
function (newDoc, oldDoc) {
  if (oldDoc) throw({ forbidden: "append-only: crea un doc nuevo, no actualices" });
  if (newDoc.type === "decision") {
    if (["PAGAR", "NO_PAGAR", "ESCALAR"].indexOf(newDoc.result) < 0)
      throw({ forbidden: "result debe ser PAGAR|NO_PAGAR|ESCALAR" });
    if (!newDoc.rule_evaluations || !newDoc.config_ref)
      throw({ forbidden: "decision requiere rule_evaluations + config_ref" });
  }
}
```

```js
// fields: values[] es append-only (nunca colapsar candidatos)
function (newDoc, oldDoc) {
  if (!oldDoc) return;
  for (var i = 0; i < oldDoc.values.length; i++) {
    if (JSON.stringify(oldDoc.values[i]) !== JSON.stringify(newDoc.values[i]))
      throw({ forbidden: "values[] es append-only" });
  }
}
```

```js
// documents: gate de formatos + estados válidos
var SUPPORTED = { pdf: 1, csv: 1, xlsx: 1, jpg: 1, png: 1 };
function (newDoc, oldDoc) {
  if (newDoc.type !== "document") return;
  newDoc.format_status = SUPPORTED[newDoc.source_format] ? "supported" : "tentative";
  if (newDoc.status &&
      ["pendiente", "PAGAR", "NO_PAGAR", "ESCALAR"].indexOf(newDoc.status) < 0)
    throw({ forbidden: "status inválido" });
}
```

## 10 · Índices Mango y vistas

Mango:

```json
{ "index": { "fields": ["status", "received_at"] },          "name": "by_status",  "db": "documents" },
{ "index": { "fields": ["sha256"] },                          "name": "by_sha",     "db": "documents" },
{ "index": { "fields": ["source_format", "format_status"] },  "name": "by_format",  "db": "documents" },
{ "index": { "fields": ["invoice_id", "created_at"] },        "name": "by_invoice", "db": "decisions" },
{ "index": { "fields": ["result", "created_at"] },            "name": "by_result",  "db": "decisions" },
{ "index": { "fields": ["invoice_id", "timestamp"] },         "name": "by_invoice", "db": "overrides" }
```

Vistas (design docs):

| Vista | Uso |
|---|---|
| `documents/by_status` | cola de revisión (`key="ESCALAR"`), cola de reanudación (`key="pendiente"`) |
| `documents/by_sha` | dedupe (junto al doc alias) |
| `decisions/by_result` + reduce `_count` | dashboards por lote |
| `fields/low_confidence` | campos cuyo mejor candidato < umbral → alimenta la política ESCALAR |
| `evidence/by_invoice` | traza completa por factura (UI §7) |

Las lookups de caché no necesitan vista: `_id` determinista + `_bulk_get`.

## 11 · Notas de operación (§3/§5/§8)

- **Idempotencia**: `PUT` con `_id` determinista; `409` = hecho, reusar.
  Lotes con `_bulk_docs`; restauración de evidencia con `new_edits=false`.
- **Reanudabilidad**: pendientes = `documents` con `status: "pendiente"`;
  un crash a mitad de lote pierde como máximo el item en vuelo.
- **Ledger**: `_changes` continuo con `include_docs=true`; filtrar con
  `_doc_ids` para espejar solo `decisions` al JSONL local.
- **Replicación** hacia la UI: `documents` (con attachments), `fields`,
  `decisions`, `overrides`; `features`/`evidence` pueden quedarse en el
  servidor si no quieres blobs en la máquina de revisión.
- **Compaction**: segura en DBs append-only; en `documents`, programar
  compact + `_view_cleanup` tras cada lote (las revs viejas de attachments
  ocupan hasta que se compacta).
- **Quórums** (cluster): escrituras con `w=majority` para evidencia y
  decisiones antes de dar un item por terminado.
