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


# Códigos estables de la causa de un UNKNOWN (contrato: reglas, store e informes).
UNKNOWN_SIN_CAMPO = "SIN_CAMPO"  # el campo no se extrajo o vino vacío
UNKNOWN_SIN_CANDIDATO_VALIDO = (
    "SIN_CANDIDATO_VALIDO"  # había candidatos, ninguno supera formato y umbral
)
UNKNOWN_CONFIANZA_BAJA = "CONFIANZA_BAJA"  # el mejor candidato no llega al umbral de la regla
UNKNOWN_NO_PARSEABLE = "NO_PARSEABLE"  # hay valor pero no se puede interpretar (fecha, …)
UNKNOWN_CRUZ_NO_POSIBLE = "CRUZ_NO_POSIBLE"  # falta el dato con el que cruzar (maestro/ERP)
UNKNOWN_OTRO = "OTRO"  # motivo sin categoría estable

UNKNOWN_CODES = (
    UNKNOWN_SIN_CAMPO,
    UNKNOWN_SIN_CANDIDATO_VALIDO,
    UNKNOWN_CONFIANZA_BAJA,
    UNKNOWN_NO_PARSEABLE,
    UNKNOWN_CRUZ_NO_POSIBLE,
    UNKNOWN_OTRO,
)


def classify_unknown_reason(reason: str) -> str:
    """Clasifica un motivo UNKNOWN (texto) en su código estable.

    Solo para filas legacy sin reason_code: las reglas nuevas ya emiten el
    código estructural desde escoger/pick. Determinista: misma cadena ⇒ mismo código.
    """
    r = (reason or "").strip()
    # quita envolturas del tipo "NIF no fiable: <motivo del colapso>"
    while True:
        head, sep, tail = r.partition(": ")
        if sep and "no fiable" in head.lower():
            r = tail.strip()
            continue
        break
    low = r.lower()
    if low.startswith("sin campo"):
        return UNKNOWN_SIN_CAMPO
    if "ningún candidato" in low or low.startswith("sin candidatos"):
        return UNKNOWN_SIN_CANDIDATO_VALIDO
    if "con confianza" in low and "< umbral" in low:
        return UNKNOWN_CONFIANZA_BAJA
    if "no parseable" in low:
        return UNKNOWN_NO_PARSEABLE
    if "fuera de maestro" in low or "no existe en el erp" in low:
        return UNKNOWN_CRUZ_NO_POSIBLE
    return UNKNOWN_OTRO


@dataclass(slots=True)
class ExtractionFeature:
    """Material en crudo del PDF, sin interpretar (fase 1)."""

    type: str  # "pdf_text" | "page_image" | "qr_payload" | "table" | ...
    extraction_method: str  # "pypdf" | "pypdfium2" | "zxing" | "tesseract" | "vlm" | "typesafe_jev" | "cloud_vlm" | "skipped:<reason>"
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
    chosen_candidates: dict[str, str] = field(
        default_factory=dict
    )  # field -> candidate elegido y por qué
    reason_code: str = ""  # si UNKNOWN: causa estable (types.UNKNOWN_*); si no, vacío


@dataclass(slots=True)
class ConfigSnapshot:
    """Configuración activa en el momento de la decisión."""

    thresholds: dict[str, Any] = field(default_factory=dict)
    extractor_versions: dict[str, str] = field(default_factory=dict)
    master_sha256: str = ""
    config_version: str = ""
    # Resultado del motor si la regla devuelve FAIL (configurable, nunca PAGAR).
    rule_outcomes: dict[str, str] = field(default_factory=dict)


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
    extraction_ms: int = 0
    parser_ms: int = 0
    evaluation_ms: int = 0
    total_ms: int = 0
    timings: dict[str, int] = field(default_factory=dict)

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
