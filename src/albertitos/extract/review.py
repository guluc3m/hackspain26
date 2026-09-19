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
KIND_CONSUMIDO = "consumido"  # marcador append-only de override consumido (T38-F6)


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
        self._seen: set[str] | None = None  # lazy: shas ya encolados (T33-M3)

    @property
    def review_path(self) -> Path:
        return self.root / REVIEW_FILE

    @property
    def overrides_path(self) -> Path:
        return self.root / OVERRIDES_FILE

    def _seen_page_shas(self) -> set[str]:
        """Page shas ya encolados, leídos UNA VEZ por instancia (T33-M3).

        `enqueue` es O(1) amortizado en vez de releer el fichero completo en
        cada llamada (la cola crece con el lote); el estado en disco sigue
        siendo la fuente de verdad al (re)construir la instancia.
        """
        if self._seen is None:
            self._seen = {
                rec.get("page_sha256") for rec in self._read(self.review_path)
            }
        return self._seen

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
        if page_sha256 in self._seen_page_shas():
            return {}
        self._seen.add(page_sha256)
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

    def read_overrides_pendientes(self) -> list[dict[str, Any]]:
        """Overrides aún no consumidos por el pipeline (T38-F6).

        Un override queda CONSUMIDO cuando el runner lo inyecta como
        candidato y recalcula la decisión; el marcador `kind=consumido` es
        append-only (el histórico jamás se reescribe ni se borra).
        """
        consumidas = {
            self._clave_consumido(rec)
            for rec in self._read(self.overrides_path)
            if rec.get("kind") == KIND_CONSUMIDO
        }
        return [
            rec
            for rec in self.read_overrides()
            if rec.get("kind") != KIND_CONSUMIDO
            and self._clave_consumido(rec) not in consumidas
        ]

    @staticmethod
    def _clave_consumido(rec: dict[str, Any]) -> tuple:
        """Identidad de un override (misma corrección, mismo momento)."""
        return (
            rec.get("invoice_id"),
            rec.get("file_id"),
            rec.get("campo"),
            str(rec.get("valor")),
            rec.get("cuando"),
        )

    def marcar_consumidas(self, overrides: list[dict[str, Any]]) -> int:
        """Append de marcadores `kind=consumido` para los overrides dados.

        Idempotente en la práctica: si el runner crashea entre inyectar y
        marcar, el re-run re-inyecta el override (misma decisión byte a
        byte — el motor es determinista) y vuelve a marcar.
        """
        if not overrides:
            return 0
        self.root.mkdir(parents=True, exist_ok=True)
        ahora = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
        with self.overrides_path.open("a", encoding="utf-8") as fh:
            for rec in overrides:
                fh.write(
                    json.dumps(
                        {
                            "kind": KIND_CONSUMIDO,
                            "invoice_id": rec.get("invoice_id", ""),
                            "file_id": rec.get("file_id", ""),
                            "campo": rec.get("campo", ""),
                            "valor": str(rec.get("valor", "")),
                            "cuando": rec.get("cuando", ""),
                            "consumido": ahora,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                )
        return len(overrides)

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
