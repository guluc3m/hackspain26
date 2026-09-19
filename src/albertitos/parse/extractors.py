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
_TOTAL_RE = re.compile(r"(?:TOTAL|TOTAL\s+FACTURA|IMPORTE\s+TOTAL)\s*(?:\(\s*IVA\s+INCLUIDO\s*\))?\s*[.:…\s]*\s*([0-9][\d.,]*)", re.IGNORECASE)
_IVA_LINE_RE = re.compile(r"(?:CUOTA\s+)?IVA\b(.*)", re.IGNORECASE)
_AMOUNT_RE = re.compile(r"(?:EUR\s*)?([0-9][\d.,]*)", re.IGNORECASE)
_RATE_RE = re.compile(r"([0-9]{1,2}(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_BASE_RE = re.compile(r"(?:BASE(?:\s+IMPO[NV]IBLE)?|IMPORTE\s+BASE)\s*[.:…\s]*\s*([0-9][\d.,]*)", re.IGNORECASE)
_TOTAL_RE = re.compile(r"(?:TOTAL\s+FACTURA|TOTAL\s+A\s+PAGAR|IMPORTE\s+TOTAL|TOTAL)\s*(?:\(\s*IVA\s+INCLUIDO\s*\))?\s*[.:…\s]*\s*([0-9][\d.,]*)", re.IGNORECASE)
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
    if not m:
        m = re.search(r"Importe\s+base\s*:\s*([0-9][\d.,]*)", text, re.IGNORECASE)
    return (normalizers.parse_amount(m.group(1)), 0.6) if m else (None, 0.0)


def _iva_lines(text: str) -> list[str]:
    """Resto de cada línea que menciona IVA (soporta "IVA (21%): 522,90",
    "Cuota IVA: EUR 413,61", "IVA.......... 181,80", "IVA 21% 522,90")."""
    return [m.group(1) for m in _IVA_LINE_RE.finditer(text)]


def _line_numbers(line: str) -> list[str]:
    """Números de la línea tras quitar relleno (puntos de guía, EUR...)."""
    return [m.group(1) for m in _AMOUNT_RE.finditer(line)]


def _iva_rate(text: str) -> tuple[Any, float]:
    for line in _iva_lines(text):
        m = _RATE_RE.search(line)
        if m:
            return (int(m.group(1)), 0.6)
    return (None, 0.0)


def _iva_amount(text: str) -> tuple[Any, float]:
    for line in _iva_lines(text):
        rate = _RATE_RE.search(line)
        numbers = [n for n in _line_numbers(line) if not rate or n != rate.group(1)]
        if numbers:  # el número que no es el % es el importe
            return (normalizers.parse_amount(numbers[-1]), 0.6)
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
