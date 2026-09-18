"""Rung-1 plausibility gate: is this text layer *usable*?

Broken CID fonts yield confident mojibake, so a non-empty text layer is NOT
enough. We check glyph corruption ("(cid:N)", U+FFFD, control chars) and a
dictionary ratio against a compact Spanish/English invoice vocabulary.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from albertitos.extract.config import ExtractionConfig

_CID_RE = re.compile(r"\(cid:\d+\)")
_TOKEN_RE = re.compile(r"[A-Za-zÁÉÍÓÚÑÜáéíóúñü]{2,}")
_VOWELS = set("aeiouáéíóúü")

# Compact vocabulary: frequent Spanish/English words + invoice domain words.
# Keeping it small and embedded avoids a heavy dependency; the ratio gate only
# needs to tell mojibake apart from real prose.
_WORDS = frozenset(
    ["la", "el", "los", "las", "del", "se", "por", "un", "una", "con", "para", "su", "sus", "al", "lo", "como", "mas", "más", "pero", "le", "ya", "o", "este", "esta", "estos", "estas", "eso", "esa", "ese", "si", "sí", "porque", "entre", "cuando", "muy", "sin", "sobre", "tambien", "también", "me", "hasta", "hay", "donde", "quien", "desde", "todo", "toda", "todos", "todas", "uno", "una", "nos", "ni", "contra", "otros", "otras", "otro", "otra", "ellos", "ellas", "esto", "mi", "mis", "tu", "tus", "te", "antes", "algunos", "algunas", "qué", "que", "cual", "cuales", "poco", "ella", "estar", "ser", "son", "fue", "era", "tiene", "tienen", "hacer", "años", "año", "dos", "tres", "cuatro", "cinco", "fecha", "factura", "facturas", "numero", "número", "nif", "cif", "iva", "base", "importe", "importes", "total", "totales", "pedido", "pedidos", "proveedor", "proveedores", "cliente", "clientes", "pago", "pagar", "pagos", "vencimiento", "euros", "euro", "cantidad", "precio", "descuento", "subtotal", "albaran", "albarán", "referencia", "unidad", "unidades", "direccion", "dirección", "telefono", "teléfono", "correo", "email", "suministro", "transporte", "papelería", "papeleria", "informática", "informatica", "material", "materiales", "servicio", "servicios", "empresa", "sl", "s", "a", "sociedad", "limitada", "iban", "cuenta", "fecha", "emision", "emisión", "vencido", "neto", "bruto", "tipo", "porcentaje", "nº", "n", "invoice", "date", "total", "due", "amount", "vendor", "order", "payment", "qty", "unit", "price", "tax", "net", "gross", "ref", "reference", "street", "madrid", "barcelona", "valencia", "sevilla", "bilbao"]
)


@dataclass
class TextPlausibility:
    """Result of the usability gate, with its measured terms."""

    usable: bool
    reason: str
    n_chars: int
    cid_per_kchar: float
    replacement_ratio: float
    dict_ratio: float


def _dict_ratio(text: str) -> float:
    tokens = _TOKEN_RE.findall(text)
    if not tokens:
        return 0.0
    plausible = 0
    for tok in tokens:
        low = tok.lower()
        if low in _WORDS:
            plausible += 1
        elif any(ch in _VOWELS for ch in low):
            plausible += 1  # vowel-bearing token: shaped like a word
    return plausible / len(tokens)


def check_text_usability(text: str, cfg: ExtractionConfig) -> TextPlausibility:
    n = len(text)
    if n < cfg.min_text_chars:
        return TextPlausibility(False, f"too-short:{n}<{cfg.min_text_chars}", n, 0.0, 0.0, 0.0)

    cid_count = len(_CID_RE.findall(text))
    cid_per_kchar = cid_count * 1000.0 / n
    if cid_count and cid_per_kchar > cfg.max_cid_per_kchar:
        return TextPlausibility(
            False, f"cid-fonts:{cid_count} occurrences", n, cid_per_kchar, 0.0, 0.0
        )

    replacement = text.count("\ufffd") + sum(1 for ch in text if ord(ch) < 32 and ch not in "\n\t\r")
    repl_ratio = replacement / n
    if repl_ratio > cfg.max_replacement_ratio:
        return TextPlausibility(
            False, f"replacement-chars:{replacement}", n, cid_per_kchar, repl_ratio, 0.0
        )

    ratio = _dict_ratio(text)
    if ratio < cfg.min_dict_ratio:
        return TextPlausibility(
            False, f"dict-ratio:{ratio:.2f}<{cfg.min_dict_ratio}", n, cid_per_kchar, repl_ratio, ratio
        )

    return TextPlausibility(True, "usable", n, cid_per_kchar, repl_ratio, ratio)
