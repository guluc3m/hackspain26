"""Extractores de campos: regex/heurísticas (y, más adelante, LLM).

Cada extractor devuelve (valor | None, confianza en [0,1]). Varios extractores
pueden leer el mismo campo: todos los valores se guardan.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from . import normalizers

Extractor = Callable[[str], tuple[Any, float]]
NamedExtractor = tuple[str, str, Extractor]  # (field_type, nombre, extractor)

_NIF_RE = re.compile(r"\b([XYZ]\d{7}[A-Z]|[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]|\d{8}[A-Z])\b")
_IBAN_RE = re.compile(r"\bES\d{2}(?:[ ]?\d{4}){5}\b")
_TOTAL_RE = re.compile(r"(?:TOTAL|IMPORT[EO] TOTAL)\s*:?\s*([0-9][\d.,]*)", re.IGNORECASE)
_IVA_RE = re.compile(r"\bIVA\s*:?\s*([0-9][\d.,]*)\s*(%?)", re.IGNORECASE)
_BASE_RE = re.compile(r"(?:BASE(?:\s+IMPO[NV]IBLE)?)\s*:?\s*([0-9][\d.,]*)", re.IGNORECASE)
_FECHA_RE = re.compile(r"\b(\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4})\b")
_PEDIDO_RE = re.compile(r"(?:PEDIDO|ORDEN|N[ºO]\.?\s*PEDIDO)\s*:?\s*([A-Z0-9-]{3,})", re.IGNORECASE)


def _nif(text: str) -> tuple[Any, float]:
    m = _NIF_RE.search(text)
    return (normalizers.normalize_nif(m.group(1)), 0.8) if m else (None, 0.0)


def _iban(text: str) -> tuple[Any, float]:
    m = _IBAN_RE.search(text)
    return (normalizers.normalize_iban(m.group(0)), 0.9) if m else (None, 0.0)


def _total(text: str) -> tuple[Any, float]:
    m = _TOTAL_RE.search(text)
    return (normalizers.parse_amount(m.group(1)), 0.7) if m else (None, 0.0)


def _base(text: str) -> tuple[Any, float]:
    m = _BASE_RE.search(text)
    return (normalizers.parse_amount(m.group(1)), 0.6) if m else (None, 0.0)


def _iva_rate(text: str) -> tuple[Any, float]:
    m = _IVA_RE.search(text)
    return (int(m.group(1)), 0.6) if m and m.group(2) == "%" else (None, 0.0)


def _iva_amount(text: str) -> tuple[Any, float]:
    for m in _IVA_RE.finditer(text):
        if m.group(2) != "%":
            return (normalizers.parse_amount(m.group(1)), 0.6)
    return (None, 0.0)


def _fecha(text: str) -> tuple[Any, float]:
    m = _FECHA_RE.search(text)
    return (m.group(1), 0.6) if m else (None, 0.0)


def _pedido(text: str) -> tuple[Any, float]:
    m = _PEDIDO_RE.search(text)
    return (m.group(1).upper(), 0.7) if m else (None, 0.0)


def all_extractors() -> list[NamedExtractor]:
    return [
        ("nif", "regex_nif", _nif),
        ("iban", "regex_iban", _iban),
        ("total", "regex_total", _total),
        ("base", "regex_base", _base),
        ("iva_rate", "regex_iva_rate", _iva_rate),
        ("iva_amount", "regex_iva_amount", _iva_amount),
        ("fecha", "regex_fecha", _fecha),
        ("pedido", "regex_pedido", _pedido),
    ]
