"""Review queue — escalated pages, non-blocking (AGENTS.md §7, ticket T7).

Writes append-only JSONL in `.sdd/review-queue/` using the record schema the
UI already consumes (`src/albertitos/ui/ledger.py`, worker/w3):

  {"kind": "evidence", ...}  — the rung-5 evidence row (provenance included)
  {"kind": "fields",   ...}  — candidate readings side by side + page image b64

Human overrides arrive from the UI at `.sdd/review-queue/overrides.jsonl`
(schema: OverrideView). They feed EXTRACTION ONLY — the decision is always
recomputed deterministically by the rule engine. This module only reads them;
it never duplicates the override mechanism.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

REVIEW_FILE = "review.jsonl"
OVERRIDES_FILE = "overrides.jsonl"


def _candidate_confidence(feat) -> float:
    """A confidence per candidate reading, derived from what the rung measured.

    pdf_text → dictionary-ratio terms are not stored on the feature, so the
    gate outcome (accepted) maps to 1.0; OCR/VLM rungs store coverage terms.
    Unknown ⇒ 0.0 (never invented).
    """
    data = feat.data
    if isinstance(data, dict):
        conf = data.get("field_coverage")
        if isinstance(conf, (int, float)):
            return float(conf)
    return 1.0 if feat.type == "pdf_text" else 0.0


def _readings_from_features(features: list) -> dict[str, list[dict[str, Any]]]:
    """All candidate readings of one page, one candidate per extractor."""
    lecturas: list[dict[str, Any]] = []
    qrs: list[dict[str, Any]] = []
    for feat in features:
        if feat.skipped or feat.type in {"page_image"}:
            continue
        if feat.type == "qr_payload":
            qrs.append(
                {
                    "extractor": feat.extraction_method,
                    "value": feat.data,
                    "confidence": 1.0,
                }
            )
            continue
        if feat.type == "pdf_text":
            value = feat.data if isinstance(feat.data, str) else str(feat.data)
        elif isinstance(feat.data, dict) and "text" in feat.data:
            value = feat.data.get("text", "")
        elif isinstance(feat.data, dict) and "raw" in feat.data:
            value = feat.data.get("raw", "")
        else:
            value = str(feat.data)
        if not value:
            continue
        lecturas.append(
            {
                "extractor": feat.extraction_method,
                "value": value,
                "confidence": _candidate_confidence(feat),
            }
        )
    fields: dict[str, list[dict[str, Any]]] = {}
    if lecturas:
        fields["lectura_pagina"] = lecturas
    if qrs:
        fields["qr_payload"] = qrs
    return fields


class ReviewQueue:
    """Append-only queue of escalated pages. Never blocks the batch."""

    def __init__(self, root: Path | str):
        self.root = Path(root)

    @property
    def review_path(self) -> Path:
        return self.root / REVIEW_FILE

    @property
    def overrides_path(self) -> Path:
        return self.root / OVERRIDES_FILE

    def enqueue(
        self,
        *,
        invoice_id: str,
        file_id: str,
        page: int,
        page_sha256: str,
        motivo: str,
        features: list,
        cloud_ok: bool | None,
        cloud_model: str,
        config_version: str,
        png_bytes: bytes | None,
        extra_provenance: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """One escalated page: page image + every candidate reading + provenance.

        Records follow ui/ledger.py's schema (kind: evidence / fields) so the
        UI can display them unchanged. Returns the fields record written.
        """
        now = time.time()
        # idempotencia: re-procesar una página cacheada NO re-encola ni duplica
        if any(
            rec.get("page_sha256") == page_sha256 for rec in self._read(self.review_path)
        ):
            return {}
        fields = _readings_from_features(features)
        record = {
            "kind": "fields",
            "invoice_id": invoice_id,
            "file_id": file_id,  # exact PDF filename, never normalised
            "page": page,
            "page_sha256": page_sha256,
            "estado": "PENDIENTE",
            "creado": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)),
            "fields": fields,
            "page_images": {str(page): base64.b64encode(png_bytes).decode()} if png_bytes else {},
            "provenance": {
                "cloud_ok": cloud_ok,
                "cloud_model": cloud_model,
                "config_version": config_version,
                "motivo": motivo,
                **(extra_provenance or {}),
            },
        }
        self.root.mkdir(parents=True, exist_ok=True)
        with self.review_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record

    def read_pending(self) -> list[dict[str, Any]]:
        """Review items still PENDIENTE, in enqueue order."""
        return [
            rec
            for rec in self._read(self.review_path)
            if rec.get("estado") == "PENDIENTE"
        ]

    def read_overrides(self) -> list[dict[str, Any]]:
        """Human overrides enqueued by the UI (OverrideView schema).

        Feeds EXTRACTION ONLY: the parser treats each as one more candidate
        with provenance; the decision is recomputed by the rule engine.
        """
        return self._read(self.overrides_path)

    @staticmethod
    def _read(path: Path) -> list[dict[str, Any]]:
        if not path.is_file():
            return []
        out: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # corrupt line never blocks the queue
                if isinstance(rec, dict):
                    out.append(rec)
        return out
