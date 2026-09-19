"""Contrato de datos del sistema: features, fields, reglas y decisiones.

Este módulo es compartido por pipeline, store y API (una sola herramienta,
un solo motor). Ver docs/report/architecture.typ.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


def now() -> float:
    return time.time()


class Result(StrEnum):
    PAGAR = "PAGAR"
    NO_PAGAR = "NO_PAGAR"
    ESCALAR = "ESCALAR"


class RuleVerdict(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


@dataclass(slots=True)
class ExtractionFeature:
    """Material en crudo del PDF, sin interpretar (fase 1)."""

    type: str  # "pdf_text" | "page_image" | "qr_payload" | "table" | ...
    extraction_method: str  # "pypdf" | "pypdfium2" | "zxing" | "tesseract" | "vlm" | "cloud_vlm" | "skipped:<reason>"
    timestamp: float = field(default_factory=now)
    data: str | bytes | object = ""
    page: int | None = None  # 0-indexed; None = nivel documento
    sha256: str = ""
    extractor_version: str = ""
    latency_ms: int = 0
    confidence: float | None = None


@dataclass(slots=True)
class Candidate:
    """Una lectura posible de un campo. Nunca se colapsan en el store."""

    extractor: str
    value: str | int | float | dict[str, Any] | None
    confidence: float  # [0, 1]


@dataclass(slots=True)
class ExtractionField:
    """Campo interpretado por el parser; conserva TODOS los candidatos (fase 2)."""

    type: str  # "nif" | "iban" | "total" | "iva_amount" | "fecha" | "pedido" | ...
    timestamp: float = field(default_factory=now)
    values: list[Candidate] = field(default_factory=list)

    def add(self, extractor: str, value: Any, confidence: float) -> None:
        if 0.0 <= confidence <= 1.0:
            self.values.append(Candidate(extractor=extractor, value=value, confidence=confidence))


@dataclass(slots=True)
class RuleEvaluation:
    """Veredicto de una regla y los valores de campo que consumió."""

    code: str  # p.ej. "TOTALS_MUST_MATCH"
    verdict: RuleVerdict
    reason: str
    consumed: dict[str, Any] = field(default_factory=dict)
    chosen_candidates: dict[str, str] = field(default_factory=dict)  # field -> candidate elegido y por qué


@dataclass(slots=True)
class ConfigSnapshot:
    """Configuración activa en el momento de la decisión."""

    rule_set_version: str
    thresholds: dict[str, Any] = field(default_factory=dict)
    extractor_versions: dict[str, str] = field(default_factory=dict)
    master_sha256: str = ""
    config_version: str = ""


@dataclass(slots=True)
class Decision:
    """Salida del motor: resultado + reglas que lo produjeron + snapshot de config.

    Sin marca de tiempo: el motor es puro; el store sella la hora de recepción.
    """

    invoice_id: str  # UUID interno estable
    file_id: str  # nombre exacto del PDF de entrada
    result: Result
    rule_evaluations: list[RuleEvaluation] = field(default_factory=list)
    config_snapshot: ConfigSnapshot | None = None


@dataclass(slots=True)
class Override:
    """Corrección humana con procedencia; afecta solo a la extracción."""

    invoice_id: str
    field_type: str
    before: Any
    after: Any
    who: str
    rung: str  # desde qué escalón se corrige
    reason: str = ""
    timestamp: float = field(default_factory=now)
