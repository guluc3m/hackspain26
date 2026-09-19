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


# ------------------------------------------------- consumo de overrides (T38-F6)

def leer_overrides_pendientes(ruta_overrides: Path) -> list[dict[str, Any]]:
    """Overrides pendientes (schema OverrideView) del fichero de cola.

    Tolerante a líneas corruptas; devuelve TODOS los pendientes — el llamador
    filtra por file_id/invoice_id."""
    if not Path(ruta_overrides).is_file():
        return []
    pendientes: list[dict[str, Any]] = []
    for linea in Path(ruta_overrides).read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            rec = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            pendientes.append(rec)
    return pendientes


def aplicar_overrides(fields: list, pendientes: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Inyecta cada override como CANDIDATO humano de confianza 1.0 en su campo.

    El override alimenta SOLO la extracción (AGENTS.md §7): entra como una
    lectura más con provenance y la decisión la recalcula el motor. El
    candidato humano va PRIMERO en `values` (precedencia de corrección humana
    documentada; los motores que colapsan con el 1er candidato usan el dato
    humano — los que evalúan todos, lo evalúan todos).

    Devuelve la lista de {campo, valor} aplicadas."""
    from albertitos.types import Candidate, ExtractionField

    aplicadas: list[dict[str, str]] = []
    for ov in pendientes:
        campo, valor = str(ov.get("campo", "")).strip(), str(ov.get("valor", ""))
        if not campo or not valor:
            continue
        candidato = Candidate(
            extractor="humano",
            value=valor,
            confidence=1.0,
            feature_ref=f"override:{ov.get('cuando', '')}",
        )
        existente = next((f for f in fields if f.type == campo), None)
        if existente is None:
            fields.append(ExtractionField(type=campo, timestamp=time.time(), values=[candidato]))
        else:
            existente.values.insert(0, candidato)
        aplicadas.append({"campo": campo, "valor": valor})
    return aplicadas


def marcar_consumidas(ruta_overrides: Path, consumidas: list[dict[str, Any]]) -> None:
    """Saca las consumidas de la cola (reescribe) y las sella en
    `overrides.consumidos.jsonl` (provenance conservada, nunca se borra)."""
    ruta = Path(ruta_overrides)
    if not consumidas or not ruta.is_file():
        return
    claves = {
        (str(o.get("file_id", "")), str(o.get("campo", "")), str(o.get("valor", "")))
        for o in consumidas
    }
    restantes: list[str] = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        if not linea.strip():
            continue
        try:
            rec = json.loads(linea)
        except json.JSONDecodeError:
            restantes.append(linea)
            continue
        clave = (str(rec.get("file_id", "")), str(rec.get("campo", "")), str(rec.get("valor", "")))
        if clave not in claves:
            restantes.append(linea)
    tmp = ruta.with_suffix(".jsonl.tmp")
    tmp.write_text(("\n".join(restantes) + "\n") if restantes else "", encoding="utf-8")
    tmp.replace(ruta)
    consumidos = ruta.with_name("overrides.consumidos.jsonl")
    with consumidos.open("a", encoding="utf-8") as fh:
        for o in consumidas:
            o["consumido_en"] = time.strftime("%Y-%m-%d %H:%M:%S")
            fh.write(json.dumps(o, ensure_ascii=False) + "\n")
