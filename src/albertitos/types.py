"""Nuclear types — contract from docs/report/architecture.typ.

Do not change field semantics without an ADR. The decision engine is
deterministic and pure: same fields + same config ⇒ same output.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------- extraction


@dataclass
class ExtractionFeature:
    """Raw material lifted from a PDF. No interpretation ever happens here."""

    type: str  # "pdf_text" | "page_image" | "qr_payload" | "table" | ...
    extraction_method: str  # "pypdf" | "pypdfium2" | "zxing" | "tesseract" | "vlm" | "cloud_vlm"
    timestamp: float
    data: str | bytes | dict[str, Any]
    page: int | None = None  # 1-based page index; extraction is per-page
    sha256: str = ""
    latency_ms: int = 0
    skipped: str | None = None  # "skipped:<reason>" when a rung is unavailable


@dataclass
class Candidate:
    """One reading of one field. Values are NEVER collapsed in the store."""

    extractor: str
    value: str | float | dict[str, Any]
    confidence: float  # [0, 1]
    feature_ref: str = ""  # which ExtractionFeature produced it


@dataclass
class ExtractionField:
    type: str  # "nif" | "iban" | "total" | "iva_amount" | "fecha" | "pedido" | ...
    timestamp: float
    values: list[Candidate]


# ---------------------------------------------------------------- decisions


@dataclass
class RuleVerdict:
    code: str  # "TOTALS_MUST_MATCH", "NIF_IN_MASTER", ...
    outcome: str  # "PASS" | "FAIL" | "UNKNOWN"
    reason: str
    consumed: dict[str, Any]  # field values the rule looked at


@dataclass
class Decision:
    invoice_id: str
    file_id: str  # exact PDF filename — never normalised
    result: str  # "PAGAR" | "NO_PAGAR" | "ESCALAR"
    rule_verdicts: list[RuleVerdict]
    config_snapshot: dict[str, Any]


@dataclass
class EvidenceRow:
    """One row per stage run. No stage may return a bare string."""

    invoice_id: str
    stage: str
    extractor: str
    extractor_version: str
    config_version: str
    sha256: str
    latency_ms: int
    confidence: float | None
    outcome: str
    detail: str
    file_id: str = ""  # nombre EXACTO del PDF (join con la UI; T4)
