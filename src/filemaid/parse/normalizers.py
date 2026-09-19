"""Normalizadores: importes, fechas, NIF e IBAN. Deterministas y puros."""

from __future__ import annotations

import re


def parse_amount(raw: str) -> float | None:
    """'1.234,56 €' → 1234.56 ; '1,234.56' → 1234.56 ; '¥ 773,000' → 773000.0."""
    cleaned = raw.strip()
    cleaned = re.sub(
        r"(?i)\b(?:EUR|USD|GBP|CHF|JPY|BRL|MXN)\b|[€$£¥]|(?:R|MX)\$|Fr\.?",
        "",
        cleaned,
    )
    cleaned = cleaned.strip().replace(" ", "")
    if not cleaned:
        return None
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        if re.match(r"^\d{1,3}(?:,\d{3})+$", cleaned):
            # Standard thousands separators, all 3-digit groups (e.g. 1,000,000 or 773,000)
            cleaned = cleaned.replace(",", "")
        elif re.match(r"^\d{1,3}(?:,\d{3})+,\d{2}$", cleaned):
            # OCR artifact e.g. "1,135,20" where first comma is thousands and last is 2-digit decimal
            last_comma = cleaned.rfind(",")
            cleaned = cleaned[:last_comma].replace(",", "") + "." + cleaned[last_comma + 1:]
        elif cleaned.count(",") == 1:
            # Standard European comma decimal separator e.g. "1234,56"
            cleaned = cleaned.replace(",", ".")
        else:
            last_comma = cleaned.rfind(",")
            cleaned = cleaned[:last_comma].replace(",", "") + "." + cleaned[last_comma + 1:]
    elif "." in cleaned:
        if re.match(r"^\d{1,3}(?:\.\d{3})+$", cleaned):
            cleaned = cleaned.replace(".", "")
        elif re.match(r"^\d{1,3}(?:\.\d{3})\d{2}$", cleaned):
            # OCR artifact: dropped decimal separator e.g. 1.29288 -> 1292.88
            cleaned = cleaned.replace(".", "")
            cleaned = cleaned[:-2] + "." + cleaned[-2:]
    try:
        return round(float(cleaned), 2)
    except ValueError:
        return None


def normalize_nif(raw: str) -> str:
    cleaned = raw.strip()
    # Preserve Brazilian CNPJ format XX.XXX.XXX/XXXX-XX
    if re.fullmatch(r"\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}", cleaned):
        return cleaned
    return re.sub(r"[\s-]", "", cleaned).upper()


def normalize_iban(raw: str) -> str:
    cleaned = re.sub(r"[\s/\-.]", "", raw).upper()
    if cleaned.startswith("E5") and len(cleaned) >= 4 and cleaned[2:4].isdigit():
        cleaned = "ES" + cleaned[2:]
    return cleaned


TOLERANCE_EUR = 0.01


def amounts_match(a: float, b: float, tolerance: float = TOLERANCE_EUR) -> bool:
    return abs(a - b) <= tolerance
