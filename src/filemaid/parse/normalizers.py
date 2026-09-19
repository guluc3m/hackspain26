"""Normalizadores: importes, fechas, NIF e IBAN. Deterministas y puros."""

from __future__ import annotations

import re


def parse_amount(raw: str) -> float | None:
    """'1.234,56 €' → 1234.56 ; '1,234.56' → 1234.56."""
    cleaned = raw.strip().rstrip("€$ ").replace(" ", "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def normalize_nif(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw).upper()


def normalize_iban(raw: str) -> str:
    return re.sub(r"[\s-]", "", raw).upper()


TOLERANCE_EUR = 0.01


def amounts_match(a: float, b: float, tolerance: float = TOLERANCE_EUR) -> bool:
    return abs(a - b) <= tolerance
