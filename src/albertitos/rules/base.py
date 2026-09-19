"""Contrato de las reglas: código estable, PASS/FAIL/UNKNOWN, umbrales configurables.

Las reglas viven en código (los thresholds en configuración). Añadir una regla
no debe tocar el bloque de extracción; añadir un tipo de ficha, el motor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from albertitos.types import Candidate, ExtractionField, RuleEvaluation

from .master import MasterData


@dataclass(slots=True)
class RuleContext:
    """Todo lo que una regla puede consumir (sin I/O: ya está cargado)."""

    fields: dict[str, ExtractionField]
    master: MasterData
    thresholds: dict[str, Any] = field(default_factory=dict)

    def threshold(self, rule_code: str, key: str, default: float) -> float:
        value = self.thresholds.get(rule_code, {}).get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def pick(self, field_type: str, min_confidence: float = 0.0) -> tuple[Candidate | None, str | None]:
        """Colapso a escalar *solo aquí*: mejor candidato con confianza suficiente.

        Devuelve (candidato, None) o (None, motivo). Determinista: mayor confianza,
        desempate por nombre de extractor.
        """
        f = self.fields.get(field_type)
        if f is None or not f.values:
            return None, f"sin campo {field_type}"
        best = min(f.values, key=lambda c: (-c.confidence, c.extractor))
        if best.confidence < min_confidence:
            return None, (
                f"mejor candidato de {field_type} ({best.extractor}) con confianza "
                f"{best.confidence:.2f} < umbral {min_confidence:.2f}"
            )
        return best, None


class Rule(Protocol):
    code: str

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation: ...
