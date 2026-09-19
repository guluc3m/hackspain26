"""Chequeo de plausibilidad de la capa de texto (escalón 1).

Las fuentes CID rotas producen mojibake *con confianza*: hay que filtrarlo antes
de aceptar la capa de texto.
"""

from __future__ import annotations

import re
import unicodedata

_MIN_PRINTABLE_RATIO = 0.85
_MIN_ALNUM_RATIO = 0.35
_WORD_RE = re.compile(r"\b[\wáéíóúüñÁÉÍÓÚÜÑ]{2,}\b")
_COMMON_WORDS = {
    "factura", "fecha", "total", "iva", "base", "importe", "pedido", "proveedor",
    "nif", "iban", "euro", "euros", "pagar", "invoice", "date", "vat",
    "el", "la", "de", "y", "con", "para", "sl", "s.l", "sa", "s.a",
}


def text_is_plausible(text: str) -> bool:
    """True si el texto parece lenguaje real y no mojibake de fuentes CID."""
    if not text or not text.strip():
        return False
    printable = sum(ch.isprintable() or ch in "\n\t" for ch in text) / len(text)
    if printable < _MIN_PRINTABLE_RATIO:
        return False
    alnum = sum(ch.isalnum() or ch.isspace() for ch in text) / len(text)
    if alnum < _MIN_ALNUM_RATIO:
        return False
    words = _WORD_RE.findall(text)
    if len(words) < 5:
        return False
    known = sum(
        unicodedata.normalize("NFKC", w).lower() in _COMMON_WORDS for w in words
    )
    return known >= 2
