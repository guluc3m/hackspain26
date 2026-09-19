"""Chequeo de plausibilidad de la capa de texto (escalón 1).

Las fuentes CID rotas producen mojibake *con confianza*: hay que filtrarlo antes
de aceptar la capa de texto. Solo estadística de caracteres — sin listas de
palabras, funciona igual en cualquier idioma.
"""

from __future__ import annotations

_DEFAULTS = {
    "min_printable_ratio": 0.85,
    "min_alnum_ratio": 0.35,
    "min_words": 5,
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
    words = [w for w in text.split() if sum(ch.isalpha() for ch in w) >= 2]
    if len(words) >= cfg["min_words"]:
        return True
    # Detect vertical / 1-char wrapped text lines
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    single_char_lines = sum(1 for line in lines if len(line) == 1 and line.isalnum())
    if len(lines) >= cfg["min_words"] and single_char_lines / len(lines) >= 0.5:
        reassembled = "".join(lines)
        words = [w for w in reassembled.split() if sum(ch.isalpha() for ch in w) >= 2]
        if len(words) >= cfg["min_words"] or sum(ch.isalnum() for ch in reassembled) >= cfg["min_words"] * 3:
            return True
    return False

def min_words(thresholds: dict | None = None) -> int:
    """Umbral expuesto por si un test quiere saber cuántas palabras exige."""
    return int({**_DEFAULTS, **(thresholds or {})}["min_words"])
