"""Escoger el valor: colapso determinista de candidatos (docs/report/architecture/rules/escoger.typ).

Proceso, configurable por _field_ desde rules.yaml (sección `seleccion`):
  1. trim() de los valores de texto.
  2. Tests de formato con ID estable, seleccionables por field: quien no los
     pasa se rechaza por razón de formato (no desaparece del store: aquí solo
     se colapsa para la regla).
  3. Puntuación = confianza × peso del extractor; cada field tiene un
     _threshold_ de puntuación que hay que superar para continuar.
  4. Se escoge la puntuación máxima. Empate con valores iguales: da igual.
     Empate con valores distintos: ranking de extractores por field.

Puro y determinista: mismos candidatos + misma config ⇒ mismo elegido.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from albertitos.parse.normalizers import normalize_iban, normalize_nif, parse_amount
from albertitos.types import (
    UNKNOWN_SIN_CAMPO,
    UNKNOWN_SIN_CANDIDATO_VALIDO,
    Candidate,
    ExtractionField,
)

# ---------------------------------------------------------------- formatos

_NIF_RE = re.compile(r"^(?:[0-9]{8}[A-Z]|[XYZ][0-9]{7}[A-Z]|[A-HJNP-SUVW][0-9]{7}[0-9A-J])$")
_IBAN_RE = re.compile(r"^ES[0-9]{22}$")
_PEDIDO_RE = re.compile(r"^[A-Z]{1,2}-[0-9]{4}-[0-9]{3,4}$")
_FECHA_RE = re.compile(r"^([0-9]{1,2})[/.\-]([0-9]{1,2})[/.\-]([0-9]{2,4})$")


def _test_nif(raw: Any) -> bool:
    return bool(_NIF_RE.match(normalize_nif(str(raw))))


def _test_iban(raw: Any) -> bool:
    return bool(_IBAN_RE.match(normalize_iban(str(raw))))


def _test_pedido(raw: Any) -> bool:
    return bool(_PEDIDO_RE.match(str(raw).strip().upper()))


def _test_fecha(raw: Any) -> bool:
    m = _FECHA_RE.match(str(raw).strip())
    if m is None:
        return False
    d, mo, y = (int(g) for g in m.groups())
    if y < 100:
        y += 2000
    try:
        date(y, mo, d)
    except ValueError:
        return False
    return True


def _amount_of(raw: Any) -> float | None:
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value if math.isfinite(value) else None
    value = parse_amount(str(raw))
    return value if value is not None and math.isfinite(value) else None


def _test_amount(raw: Any) -> bool:
    return _amount_of(raw) is not None


def _test_amount_positive(raw: Any) -> bool:
    v = _amount_of(raw)
    return v is not None and v > 0.0


def _test_amount_non_negative(raw: Any) -> bool:
    v = _amount_of(raw)
    return v is not None and v >= 0.0


FORMAT_TESTS: dict[str, Callable[[Any], bool]] = {
    "NIF_FORMAT": _test_nif,
    "IBAN_FORMAT": _test_iban,
    "PEDIDO_FORMAT": _test_pedido,
    "DATE_FORMAT": _test_fecha,
    "AMOUNT_FORMAT": _test_amount,
    "AMOUNT_POSITIVE": _test_amount_positive,
    "AMOUNT_NON_NEGATIVE": _test_amount_non_negative,
}


# ---------------------------------------------------------------- config


@dataclass(slots=True)
class FieldSelection:
    """Config de selección para un _field_ (todos los valores son configuración)."""

    format_tests: tuple[str, ...] = ()
    score_threshold: float = 0.0
    extractor_weights: dict[str, float] = field(default_factory=dict)
    extractor_ranking: tuple[str, ...] = ()


def field_selection(seleccion: dict[str, Any] | None, field_type: str) -> FieldSelection:
    """Resuelve la config efectiva de un field: defaults globales + override por field."""
    cfg = seleccion or {}
    per_field = cfg.get("fields", {}).get(field_type, {}) or {}
    return FieldSelection(
        format_tests=tuple(str(t) for t in (per_field.get("format_tests") or ())),
        score_threshold=_as_float(
            per_field.get("score_threshold"), _as_float(cfg.get("default_score_threshold"), 0.0)
        ),
        extractor_weights={
            **{
                str(k): _as_float(v, 1.0)
                for k, v in (cfg.get("default_extractor_weights") or {}).items()
            },
            **{
                str(k): _as_float(v, 1.0)
                for k, v in (per_field.get("extractor_weights") or {}).items()
            },
        },
        extractor_ranking=tuple(
            str(x)
            for x in (per_field.get("extractor_ranking") or cfg.get("extractor_ranking") or ())
        ),
    )


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- selección

ELEGIDO = "ELEGIDO"


@dataclass(slots=True)
class CandidateAudit:
    """Trazabilidad del colapso: qué pasó con cada candidato."""

    extractor: str
    value: Any
    confidence: float
    score: float | None = None  # None = rechazado antes de puntuar
    status: str = ""  # ELEGIDO | RECHAZADO_FORMATO:<id> | RECHAZADO_UMBRAL | DESCARTADO_EMPATE
    reason: str = ""


@dataclass(slots=True)
class Selection:
    """Resultado del colapso: candidato elegido o motivo de la falta."""

    candidate: Candidate | None
    reason: str = ""  # motivo si no hay candidato
    reason_code: str = ""  # código estable del motivo (types.UNKNOWN_*)
    why: str = ""  # por qué se eligió el candidato (procedencia para la evidencia)
    audit: list[CandidateAudit] = field(default_factory=list)


def escoger(f: ExtractionField, sel: FieldSelection) -> Selection:
    """Colapsa un ExtractionField a un candidato según el proceso de escoger.typ."""
    if not f.values:
        return Selection(
            None, reason=f"sin candidatos para {f.type}", reason_code=UNKNOWN_SIN_CAMPO
        )

    audit: list[CandidateAudit] = []
    vivos: list[tuple[Candidate, float]] = []
    for c in f.values:
        value = c.value.strip() if isinstance(c.value, str) else c.value
        c = Candidate(extractor=c.extractor, value=value, confidence=c.confidence)

        fail = next((t for t in sel.format_tests if not _run_test(t, c.value)), None)
        if fail is not None:
            audit.append(
                CandidateAudit(
                    c.extractor,
                    c.value,
                    c.confidence,
                    None,
                    f"RECHAZADO_FORMATO:{fail}",
                    f"no supera el test de formato {fail}",
                )
            )
            continue

        score = round(c.confidence * sel.extractor_weights.get(c.extractor, 1.0), 9)
        if score <= sel.score_threshold:
            audit.append(
                CandidateAudit(
                    c.extractor,
                    c.value,
                    c.confidence,
                    score,
                    "RECHAZADO_UMBRAL",
                    f"puntuación {score:.2f} no supera el umbral {sel.score_threshold:.2f}",
                )
            )
            continue
        audit.append(CandidateAudit(c.extractor, c.value, c.confidence, score))
        vivos.append((c, score))

    if not vivos:
        return Selection(
            None,
            reason=f"ningún candidato de {f.type} supera formato y umbral de puntuación",
            reason_code=UNKNOWN_SIN_CANDIDATO_VALIDO,
            audit=audit,
        )

    max_score = max(s for _, s in vivos)
    finalists = [(c, s) for c, s in vivos if s == max_score]

    if len(finalists) == 1:
        chosen, score = finalists[0]
        why = f"puntuación máxima {score:.2f} (confianza {chosen.confidence:.2f} × peso {sel.extractor_weights.get(chosen.extractor, 1.0):.2f})"
    elif all(c.value == finalists[0][0].value for c, _ in finalists):
        chosen, score = min(finalists, key=lambda cs: cs[0].extractor)
        why = f"empate de puntuación {score:.2f} con valores idénticos; se registra el de extractor {chosen.extractor}"
    else:
        chosen, score = min(
            finalists, key=lambda cs: _rank_key(cs[0].extractor, sel.extractor_ranking)
        )
        why = f"empate de puntuación {score:.2f} con valores distintos; desempate por ranking de extractores"

    for a in audit:
        if a.status:
            continue
        if (a.extractor, str(a.value), a.confidence) == (
            chosen.extractor,
            str(chosen.value),
            chosen.confidence,
        ):
            a.status = ELEGIDO
        elif a.score == max_score:
            a.status = "DESVANTAJA_DESEMPATE"
            a.reason = "misma puntuación que el elegido; el desempate no le favorece"
        else:
            a.status = "MENOR_PUNTUACION"
    return Selection(chosen, why=why, audit=audit)


def _run_test(test_id: str, value: Any) -> bool:
    test = FORMAT_TESTS.get(test_id)
    return test(value) if test is not None else True  # ID desconocido: no bloquea


def _rank_key(extractor: str, ranking: tuple[str, ...]) -> tuple[int, str]:
    try:
        return ranking.index(extractor), extractor
    except ValueError:
        return len(ranking), extractor
