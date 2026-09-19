"""Contrato de las reglas: código estable, PASS/FAIL/UNKNOWN, umbrales configurables.

Las reglas viven en código (los thresholds en configuración). Añadir una regla
no debe tocar el bloque de extracción; añadir un tipo de ficha, el motor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from albertitos.types import (
    UNKNOWN_CONFIANZA_BAJA,
    UNKNOWN_SIN_CAMPO,
    Candidate,
    ExtractionField,
    RuleEvaluation,
)

from .escoger import Selection, escoger, field_selection
from .master import MasterData


@dataclass(slots=True)
class RuleContext:
    """Todo lo que una regla puede consumir (sin I/O: ya está cargado)."""

    fields: dict[str, ExtractionField]
    master: MasterData
    thresholds: dict[str, Any] = field(default_factory=dict)
    seleccion: dict[str, Any] = field(default_factory=dict)

    def threshold(self, rule_code: str, key: str, default: float) -> float:
        value = self.thresholds.get(rule_code, {}).get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def pick(
        self, field_type: str, min_confidence: float = 0.0
    ) -> tuple[Candidate | None, str | None]:
        """Colapso a escalar *solo aquí*, según docs/report/architecture/rules/escoger.typ.

        Devuelve (candidato, None) o (None, motivo). Determinista: trim, tests
        de formato, puntuación (confianza × peso) con umbral por field y
        desempates (valores iguales; si no, ranking de extractores).
        """
        cand, why, _code = self.pick_coded(field_type, min_confidence)
        return cand, why

    def pick_coded(
        self, field_type: str, min_confidence: float = 0.0
    ) -> tuple[Candidate | None, str | None, str]:
        """Como pick(), pero devuelve también el código estable del motivo.

        (candidato, None, "") o (None, motivo, código de types.UNKNOWN_*).
        """
        sel = self.pick_detailed(field_type, min_confidence)
        if sel.candidate is None:
            return None, sel.reason, sel.reason_code
        return sel.candidate, None, ""

    def pick_detailed(self, field_type: str, min_confidence: float = 0.0) -> Selection:
        """Como pick(), pero con la trazabilidad completa del colapso (auditoría)."""
        f = self.fields.get(field_type)
        if f is None or not f.values:
            return Selection(None, reason=f"sin campo {field_type}", reason_code=UNKNOWN_SIN_CAMPO)
        sel = escoger(f, field_selection(self.seleccion, field_type))
        if sel.candidate is None:
            return sel
        if sel.candidate.confidence < min_confidence:
            return Selection(
                None,
                reason=(
                    f"mejor candidato de {field_type} ({sel.candidate.extractor}) con confianza "
                    f"{sel.candidate.confidence:.2f} < umbral {min_confidence:.2f}"
                ),
                reason_code=UNKNOWN_CONFIANZA_BAJA,
                audit=sel.audit,
            )
        return sel


class Rule(Protocol):
    code: str

    def evaluate(self, ctx: RuleContext) -> RuleEvaluation: ...
