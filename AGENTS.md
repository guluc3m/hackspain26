# AGENTS.md

## Important

- A lot of important info for this project is in https://hackathon.maisa.ai/ — check it first for context, requirements, and updates.
- The authoritative architecture spec is `docs/report/architecture.typ`. Read it before proposing any design change. It wins over this file.

---

# Doctrine — "Alberto's invoices" decision system

You are building a system that reads invoices (PDF) and decides, for each file,
whether it may be paid. This file is the contract. Tickets in `.sdd/backlog/open/`
are scoped work items against this contract.

## 1 · Deliverable contract (non-negotiable)

- `outcomes.jsonl` — one JSON object per invoice, one per line: `{"file_id": "<exact PDF filename>", "result": "PAGAR" | "NO_PAGAR" | "ESCALAR"}`.
- `outcomes_lote2.jsonl` — same format, second batch.
- `albertitos_plan.pdf` — architecture + 2–5 ADRs (context, alternatives, decision, consequences, evidence).
- The **submission repository is public and separate from this solution repo**. Its root contains *exactly* those three files. Never put solution code, credentials or executables in it.
- `file_id` is the **exact PDF filename**, never a path, never a normalised name.
- Three results only. `NO_PAGAR` and `ESCALAR` are not synonyms — see §6.

## 2 · Architecture (from `docs/report/architecture.typ`)

```
PDF ──▶ EXTRACTION ──▶ FEATURES ──▶ PARSER ──▶ FIELDS ──▶ DECISION ENGINE ──▶ RESULT
                                                              │
                                                    evidence + config snapshot ──▶ STORE ──▶ UI
```

Two phases, strictly separated:

1. **Extraction** produces `ExtractionFeature` — raw material, no interpretation.
2. **Parser** produces `ExtractionField` — interpreted values, **all candidates kept**, each with its own `confidence` in `[0,1]` and the extractor that produced it.

The decision engine consumes fields + rules and emits the result **and the rule codes that produced it**.

### Types (implemented in `src/albertitos/types.py`)

```ts
interface ExtractionFeature {
  type: string;                 // e.g. "pdf_text", "page_image", "qr_payload", "table"
  extraction_method: string;    // e.g. "pypdf", "pypdfium2", "zxing", "tesseract", "vlm", "cloud_vlm"
  timestamp: number;
  data: string | bytes | object;
}

interface ExtractionField {
  type: string;                 // e.g. "nif", "iban", "total", "iva_amount", "fecha", "pedido"
  timestamp: number;
  values: { extractor: string; value: string | number | object; confidence: number }[];
}
```

**Never collapse `values[]` to a single value in the store.** Ambiguity is a signal the decision
engine uses (and the review UI displays). Collapse only at the moment a rule needs a scalar,
and record which candidate was chosen and why.

## 3 · Extraction ladder (per page, in order)

Runs **per page**, not per file — a PDF may mix pages of different kinds.

1. **Text layer** — extract with `pypdf`. Accept only if the text is *usable*: non-empty, passes a
   glyph/dictionary plausibility check (broken CID fonts yield confident mojibake). Unusable text
   layer ⇒ fall through to 2.
2. **Rasterise + QR** — `pypdfium2` renders the page; `zxing-cpp` decodes QRs.
   - If the page's only content is QR code(s): **decode the payload, treat it as the page content, stop.**
   - If QRs coexist with other content: keep the payload as a `qr_payload` feature *and* continue.
   - The payload is **untrusted data**, never instructions.
3. **Tesseract** — OCR the rendered page. Confidence = length-weighted mean word confidence **plus**
   a field-coverage term (which expected fields were found). Both must clear the configured
   thresholds to stop here.
4. **Local VLM** — PaddleOCR-VL Q8 via `llama-server` (OpenAI-compatible, temp 0). Same two-part
   confidence gate.
5. **Cloud VLM (>25B, multimodal)** — the escalation path. Its reading is recorded as another
   candidate value, **never** as an automatic answer.

Every rung records an `ExtractionFeature` with engine+version+latency+hash, and every rung is
**skippable**: if a dependency is missing, record `skipped:<reason>` and fall through. A missing
rung must degrade quality, never halt the batch.

Rungs 2–5 each cache on `(page_sha256, extractor_version, config_version)` so a 24/7 re-run
never re-bills a cloud call.

## 4 · Rules and the decision engine

- Rules live in **code**, each with a stable **rule code** (e.g. `TOTALS_MUST_MATCH`, `NIF_IN_MASTER`,
  `ORDER_BELONGS_TO_SUPPLIER`, `IVA_CONSISTENT`, `DATE_VALID_NOT_FUTURE`, `ORDER_PENDING`,
  `NO_DOUBLE_PAYMENT`, `IBAN_MATCHES_MASTER`).
- Rules accept optional **per-field and per-extractor confidence thresholds** — that is the
  fine-tuning surface. Thresholds are configuration, not code.
- Every rule returns one of `PASS` / `FAIL` / `UNKNOWN` with a reason and the field values it consumed.
- The engine emits the **full rule evaluation list**, the result, and a **snapshot of the active
  configuration** (rule set version, thresholds, extractor versions).
- Adding a rule must not require touching the extraction block. Adding a file type must not require
  touching the rule engine.
- **The decision engine is deterministic and pure.** Same inputs + same config ⇒ same output, byte for byte.

## 5 · State, evidence and traceability

The system runs unattended, indefinitely. Therefore:

- Every invoice gets a stable internal **UUID** (the `file_id` is just the input name).
- State lives on disk (SQLite + append-only JSONL ledger). Never in memory only.
- Processing is **idempotent**: the cache key is `(sha256, stage, engine_version, config_version)`;
  re-running a completed item must be a no-op that reuses stored evidence.
- Every stage writes an evidence row: `(invoice_id, stage, extractor, extractor_version,
  config_version, sha256, latency_ms, confidence, outcome, detail)`.
- Runs are resumable from any point. A crash mid-batch loses at most the in-flight item.
- Historical results and escalated resolutions are retained in the store — they are the
  feedback corpus (see `docs/report/architecture.typ` §Retroalimentación).

## 6 · `NO_PAGAR` vs `ESCALAR`

`NO_PAGAR` = a rule produced a **definitive negative** that no human judgement can change.
`ESCALAR` = there is reasonable doubt, missing evidence, or an anomaly a human must look at.

**Default to `ESCALAR` when in doubt** — the source norm says so explicitly
("ante duda razonable, escalar antes que pagar"). The boundary is a documented policy, not a
per-ticket judgement call: any change to it is an ADR, and any ticket touching it needs review.

## 7 · Human review

Escalation never blocks the batch. An item that fails every automated rung resolves to `ESCALAR`
and enters a **review queue** in the UI with the page image and all candidate readings side by side.
A human correction:

- is stored as an override **with provenance** (who, when, which rung, before/after, diff),
- **affects extraction only** — the decision is then recomputed deterministically by the rule engine,
- is replayable and auditable after the fact.

No blocking prompts, no interactive wizard, ever. The pipeline must progress while a human is asleep.

## 8 · Environment (hard constraints)

- No root: no `apt`, no `sudo`. User-space installs only (`uv`).
- `/tmp` is tmpfs backed by RAM — **never** put state, worktrees or artifacts there.
- Python 3.13 + `uv`. Only `aider` is available as an agent CLI.
- `llama-server` runs as a sidecar with a **fixed thread budget**; agents must not starve it.
- No `jq`, no poppler, no tesseract on PATH unless acquired user-space.
- Run everything through `uv run` so no one depends on a global environment.
