"""Chequeo de plausibilidad de la capa de texto (escalón 1).

Las fuentes CID rotas producen mojibake *con confianza*: hay que filtrarlo antes
de aceptar la capa de texto.
"""

from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ]{2,}\b")
_COMMON_WORDS = {
    "factura", "fecha", "total", "iva", "base", "importe", "pedido", "proveedor",
    "nif", "iban", "euro", "euros", "pagar", "invoice", "date", "vat",
    "el", "la", "de", "y", "con", "para", "sl", "s.l", "sa", "s.a",
}

_DEFAULTS = {
    "min_printable_ratio": 0.85,
    "min_alnum_ratio": 0.35,
    "min_words": 5,
    "min_known_words": 2,
}


def text_is_plausible(text: str, thresholds: dict | None = None) -> bool:
    """True si el texto parece lenguaje real y no mojibake de fuentes CID."""
    cfg = {**_DEFAULTS, **(thresholds or {})}
    if not text or not text.strip():
        return False
    printable = sum(ch.isprintable() or ch in "\n\t" for ch in text) / len(text)
    if printable < cfg["min_printable_ratio"]:
        return False
    alnum = sum(ch.isalnum() or ch.isspace() for ch in text) / len(text)
    if alnum < cfg["min_alnum_ratio"]:
        return False
    words = _WORD_RE.findall(text)
    if len(words) < cfg["min_words"]:
        return False
    known = sum(
        unicodedata.normalize("NFKC", w).lower() in _COMMON_WORDS for w in words
    )
    return known >= cfg["min_known_words"]


