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

_CLEAN_ZW_RE = re.compile(r"[\u200b\u200c\u200d\ufeff]")

_KNOWN_CLIENT_CIFS = frozenset({"A58231074", "A68231074"})

_NIF_LABEL_RE = re.compile(
    r"(?:NIF|CIF|Tax\s+ID|N[°º]\s*TVA|USt-ID|P\.\s*IVA|N[°º/S])\s*[:.]?\s*",
    re.IGNORECASE,
)
_NIF_SPANISH_RE = r"[XYZ]\d{7}[A-Z]|[ABCDEFGHJKLMNPQRSUVW]\d{7}[0-9A-J]|\d{8}[A-Z]|\d{8,9}"
_NIF_INTL_RE = r"DE\d{9}|FR\d{11}|\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}|\d{13}"
_NIF_RE = re.compile(
    rf"(?:{_NIF_LABEL_RE.pattern})?(\b(?:{_NIF_SPANISH_RE}|{_NIF_INTL_RE})\b)",
    re.IGNORECASE,
)
_IBAN_LABEL_PAT = r"(?:IBAN|Cuenta|Account|abono(?:\s*\(IBAN\))?|\(GAN|\(IDAN)\s*[:.]?\s*"
_IBAN_RE = re.compile(
    r"\b("
    r"(?:ES|E5)\d{2}(?:[ /]?\d{4}){5}"
    r"|DE\d{2}(?:[ ]?\d{4}){4}[ ]?\d{2}"
    r"|FR\d{2}(?:[ ]?\d{4}){5}[ ]?\d{3}"
    r"|GB\d{2}[ ]?[A-Z]{4}[ ]?(?:\d{4}[ ]?){3}\d{2}"
    r"|BR\d{2}(?:[ ]?[A-Z0-9]{4,5}){5,6}[ ]?[A-Z0-9]{1,3}"
    r"|JP\d{2}(?:[ ]?\d{4}){3}[ ]?\d{3}"
    r"|[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}[ ]?[A-Z0-9]{1,4}"
    r")\b",
    re.IGNORECASE,
)
_CURRENCY_PAT = r"(?:EUR|USD|GBP|CHF|JPY|BRL|MXN|€|\$|£|Fr|¥|R\$|MX\$)"
_IVA_LINE_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:CUOTA\s+)?(?:I\.?V\.?A\.?|TVA|VAT|MWST\.?|P\.\s*IVA|IV/A|IV\.A\.|IVÁ)(?:(?=[0-9%])|\b|\s|:)(.*)",
    re.IGNORECASE,
)
_AMOUNT_RE = re.compile(rf"(?:{_CURRENCY_PAT}\s*)?([0-9][\d.,\s]*\d|[0-9])", re.IGNORECASE)
_RATE_RE = re.compile(r"([0-9]{1,2}(?:[.,]\d+)?)\s*%", re.IGNORECASE)
_BASE_LABELS = r"(?:BASE(?:\s+IMPO[NV]IBLE|\s+IMPOSABLE)?|IMPORTE\s+BASE|SUBTOTAL|SOUS-TOTAL|ZWISCHENSUMME|VALOR\s+BASE|IMPONIBILE)"
_BASE_RE = re.compile(
    rf"\b{_BASE_LABELS}\s*[.:…|\s]*(?:{_CURRENCY_PAT}\s*)?([0-9][\d.,\s]*\d|[0-9])",
    re.IGNORECASE,
)
_TOTAL_LABELS = r"(?:TOTAL\s+FACTURA|TOTAL\s+A\s+PAGAR|IMPORTE\s+TOTAL|TOTALE|GESAMT|TOTAL)"
_TOTAL_RE = re.compile(
    rf"(?<![A-Za-z0-9_-])\b{_TOTAL_LABELS}\s*(?:\(\s*IVA\s+INCLUIDO\s*\))?\s*[.:…|\s]*(?:{_CURRENCY_PAT}\s*)?([0-9][\d.,\s]*\d|[0-9])",
    re.IGNORECASE,
)
_FECHA_NUM_RE = re.compile(r"\b(\d{1,2}[/\-.][0-9]{1,2}[/\-.][0-9]{2,4})\b")
_FECHA_LABEL_RE = re.compile(
    r"(?:Fecha(?:\s+de\s+emisi[oó]n|\s+factura)?|Issue\s+date|Ausstellungsdatum|Data\s+di\s+emissione|Data\s+d['’]emissi[oó]|Data\s+de\s+emiss[aã]o|Date\s+d['’][\xe9e]mission)\s*[:.]?\s*([^\n\r]+)",
    re.IGNORECASE,
)
_FECHA_NATURAL_RE = re.compile(
    r"\b(\d{1,2})\s+de\s+(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s+de\s+(\d{4})\b",
    re.IGNORECASE,
)
_PEDIDO_RE = re.compile(
    r"\b(?:PEDIDO(?:\s+CLIENTE|\s+ASOCIADO)?|ORDEN|N[ºO]\.?\s*PEDIDO|SU\s+PEDIDO|REF\.?\s*PEDIDO|PO|P[ÉE]RDIDO|PEDI[ÑN]O|PEDIOTA|REDIDO[S]?)\s*[:|]?\s*([A-Z0-9/_-]{3,}(?:\s+[A-Z0-9/_-]+)*)",
    re.IGNORECASE,
)
_FALLBACK_PEDIDO_RE = re.compile(r"\b([A-Z]{1,2}[-/\s]\d{4}[-/\s]\d{3,4})\b", re.IGNORECASE)

_MESES: dict[str, int] = {
    # Español
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    # Inglés
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    # Francés
    "janvier": 1,
    "février": 2,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,
    # Alemán
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "maerz": 3,
    "marz": 3,
    "juni": 6,
    "juli": 7,
    "oktober": 10,
    "dezember": 12,
    # Italiano
    "gennaio": 1,
    "febbraio": 2,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "settembre": 9,
    "ottobre": 10,
    "dicembre": 12,
    # Catalán
    "gener": 1,
    "febrer": 2,
    "març": 3,
    "marc": 3,
    "maig": 5,
    "juny": 6,
    "juliol": 7,
    "agost": 8,
    "setembre": 9,
    "desembre": 12,
    # Portugués
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}

_DIAS_PALABRAS: dict[str, int] = {
    # Español
    "un": 1,
    "uno": 1,
    "primero": 1,
    "dos": 2,
    "tres": 3,
    "cuatro": 4,
    "cinco": 5,
    "seis": 6,
    "siete": 7,
    "ocho": 8,
    "nueve": 9,
    "diez": 10,
    "once": 11,
    "doce": 12,
    "trece": 13,
    "catorce": 14,
    "quince": 15,
    "dieciséis": 16,
    "dieciseis": 16,
    "diecisiete": 17,
    "dieciocho": 18,
    "diecinueve": 19,
    "veinte": 20,
    "veintiuno": 21,
    "veintidós": 22,
    "veintidos": 22,
    "veintitrés": 23,
    "veintitres": 23,
    "veinticuatro": 24,
    "veinticinco": 25,
    "veintiséis": 26,
    "veintiseis": 26,
    "veintisiete": 27,
    "veintiocho": 28,
    "veintinueve": 29,
    "treinta": 30,
    "treinta y uno": 31,
    # Inglés
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "twenty-first": 21,
    "twenty-second": 22,
    "twenty-third": 23,
    "twenty-fourth": 24,
    "twenty-fifth": 25,
    "twenty-sixth": 26,
    "twenty-seventh": 27,
    "twenty-eighth": 28,
    "twenty-ninth": 29,
    "thirtieth": 30,
    "thirty-first": 31,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    # Francés
    "premier": 1,
    "deux": 2,
    "trois": 3,
    "quatre": 4,
    "cinq": 5,
    "sept": 7,
    "huit": 8,
    "neuf": 9,
    "dix": 10,
    "onze": 11,
    "douze": 12,
    "treize": 13,
    "quatorze": 14,
    "quinze": 15,
    "seize": 16,
    "dix-sept": 17,
    "dix-huit": 18,
    "dix-neuf": 19,
    "vingt": 20,
    "vingt et un": 21,
    "vingt-deux": 22,
    "vingt-trois": 23,
    "vingt-quatre": 24,
    "vingt-cinq": 25,
    "vingt-six": 26,
    "vingt-sept": 27,
    "vingt-huit": 28,
    "vingt-neuf": 29,
    "trente": 30,
    "trente et un": 31,
    # Alemán
    "ersten": 1,
    "zweiten": 2,
    "dritten": 3,
    "vierten": 4,
    "fünften": 5,
    "fuenften": 5,
    "sechsten": 6,
    "siebten": 7,
    "achten": 8,
    "neunten": 9,
    "zehnten": 10,
    "elften": 11,
    "zwölften": 12,
    "zwoelften": 12,
    "dreizehnten": 13,
    "vierzehnten": 14,
    "fünfzehnten": 15,
    "fuenfzehnten": 15,
    "sechzehnten": 16,
    "siebzehnten": 17,
    "achtzehnten": 18,
    "neunzehnten": 19,
    "zwanzigsten": 20,
    "einundzwanzigsten": 21,
    "zweiundzwanzigsten": 22,
    "dreiundzwanzigsten": 23,
    "vierundzwanzigsten": 24,
    "fünfundzwanzigsten": 25,
    "sechsundzwanzigsten": 26,
    "siebenundzwanzigsten": 27,
    "achtundzwanzigsten": 28,
    "neunundzwanzigsten": 29,
    "dreißigsten": 30,
    "dreissigsten": 30,
    "einunddreißigsten": 31,
    "erste": 1,
    "zweite": 2,
    "dritte": 3,
    "vierte": 4,
    "fünfte": 5,
    "sechste": 6,
    "siebte": 7,
    "achte": 8,
    "neunte": 9,
    "zehnte": 10,
    # Italiano
    "primo": 1,
    "due": 2,
    "tre": 3,
    "quattro": 4,
    "cinque": 5,
    "sei": 6,
    "sette": 7,
    "otto": 8,
    "nove": 9,
    "dieci": 10,
    "undici": 11,
    "dodici": 12,
    "tredici": 13,
    "quattordici": 14,
    "quindici": 15,
    "sedici": 16,
    "diciassette": 17,
    "diciotto": 18,
    "diciannove": 19,
    "venti": 20,
    "ventuno": 21,
    "ventidue": 22,
    "ventitre": 23,
    "ventitré": 23,
    "ventiquattro": 24,
    "venticinque": 25,
    "ventisei": 26,
    "ventisette": 27,
    "ventotto": 28,
    "ventinove": 29,
    "trenta": 30,
    "trentuno": 31,
    # Catalán
    "u": 1,
    "cinc": 5,
    "sis": 6,
    "set": 7,
    "vuit": 8,
    "nou": 9,
    "deu": 10,
    "dotze": 12,
    "tretze": 13,
    "catorze": 14,
    "setze": 16,
    "disset": 17,
    "divuit": 18,
    "dinou": 19,
    "vint": 20,
    "vintiú": 21,
    "vint-i-un": 21,
    "vint-i-dos": 22,
    "vint-i-tres": 23,
    "vint-i-quatre": 24,
    "vint-i-cinc": 25,
    "vint-i-sis": 26,
    "vint-i-set": 27,
    "vint-i-vuit": 28,
    "vint-i-nou": 29,
    "trenta-un": 31,
    # Portugués
    "um": 1,
    "primeiro": 1,
    "dois": 2,
    "três": 3,
    "quatro": 4,
    "sete": 7,
    "oito": 8,
    "dez": 10,
    "doze": 12,
    "treze": 13,
    "dezesseis": 16,
    "dezessete": 17,
    "dezoito": 18,
    "dezenove": 19,
    "vinte": 20,
    "vinte e um": 21,
    "vinte e dois": 22,
    "vinte e três": 23,
    "vinte e quatro": 24,
    "vinte e cinco": 25,
    "vinte e seis": 26,
    "vinte e sete": 27,
    "vinte e oito": 28,
    "vinte e nove": 29,
    "trinta": 30,
    "trinta e um": 31,
}

_ANOS_PALABRAS: dict[str, int] = {
    "dos mil veintiséis": 2026,
    "dos mil veintiseis": 2026,
    "dos mil veinticinco": 2025,
    "dos mil veinticuatro": 2024,
    "two thousand twenty-six": 2026,
    "two thousand and twenty-six": 2026,
    "two thousand twenty-five": 2025,
    "two thousand and twenty-five": 2025,
    "two thousand twenty four": 2024,
    "two thousand twenty-four": 2024,
    "deux mille vingt-six": 2026,
    "deux mille vingt six": 2026,
    "deux mille vingt-cinq": 2025,
    "zweitausendsechsundzwanzig": 2026,
    "zweitausendfünfundzwanzig": 2025,
    "zweitausendfuenfundzwanzig": 2025,
    "duemilaventisei": 2026,
    "duemilaventicinque": 2025,
    "dos mil vint-i-sis": 2026,
    "dos mil vint-i-cinc": 2025,
}


def _parse_written_date(text: str) -> str | None:
    t = text.lower()
    m_compact = re.search(r"\b(\d{1,2})\s*de\s*([a-z]+)\s*de\s*(\d{4})", t)
    if m_compact:
        d_str, m_str, y_str = m_compact.groups()
        if m_str in _MESES:
            return f"{int(d_str):02d}/{_MESES[m_str]:02d}/{y_str}"

    sorted_months = sorted(_MESES.keys(), key=len, reverse=True)
    months_pat = "|".join(re.escape(m) for m in sorted_months)

    sorted_days = sorted(_DIAS_PALABRAS.keys(), key=len, reverse=True)
    days_pat = r"\d{1,2}|" + "|".join(re.escape(d) for d in sorted_days)

    sorted_years = sorted(_ANOS_PALABRAS.keys(), key=len, reverse=True)
    years_pat = r"\d{4}|" + "|".join(re.escape(y) for y in sorted_years)

    pat_a = re.compile(
        rf"(?:am\s+|the\s+|le\s+)?\b({days_pat})\b(?:st|nd|rd|th)?(?:\s+of\s+|\s+de\s+|\s+d['’]|\s+)({months_pat})[,\s]+(?:de\s+)?\b({years_pat})\b",
        re.IGNORECASE,
    )
    m = pat_a.search(t)
    if m:
        raw_day, raw_month, raw_year = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
        d = int(raw_day) if raw_day.isdigit() else _DIAS_PALABRAS.get(raw_day)
        mo = _MESES.get(raw_month)
        y = int(raw_year) if raw_year.isdigit() else _ANOS_PALABRAS.get(raw_year)
        if d and mo and y:
            return f"{d:02d}/{mo:02d}/{y}"

    pat_b = re.compile(
        rf"\b({months_pat})\s+({days_pat})\b(?:st|nd|rd|th)?[,\s]+\b({years_pat})\b",
        re.IGNORECASE,
    )
    m = pat_b.search(t)
    if m:
        raw_month, raw_day, raw_year = m.group(1).lower(), m.group(2).lower(), m.group(3).lower()
        d = int(raw_day) if raw_day.isdigit() else _DIAS_PALABRAS.get(raw_day)
        mo = _MESES.get(raw_month)
        y = int(raw_year) if raw_year.isdigit() else _ANOS_PALABRAS.get(raw_year)
        if d and mo and y:
            return f"{d:02d}/{mo:02d}/{y}"

    return None


def _clean_text(text: str) -> str:
    text = _CLEAN_ZW_RE.sub("", text)
    lines = text.split("\n")
    new_lines = []
    run = []

    def process_run(chars: list[str]) -> str:
        s = "".join(chars)
        s = re.sub(r":([a-zA-Z0-9])", r": \1", s)
        keywords = [
            "NIF",
            "CIF",
            "cuenta",
            "Factura",
            "Fecha",
            "pedido",
            "para",
            "Cliente",
            "Servicio",
            "base",
            "IVA",
            "TOTAL",
            "Gracias",
            "Importe",
        ]
        kw_re = r"(?<!\s)(?<!^)(?<!\b)(" + "|".join(keywords) + r")"
        s = re.sub(kw_re, r" \1", s, flags=re.IGNORECASE)
        s = re.sub(r"\b(NIF|CIF|Factura|pedido)(?=[A-Z0-9])", r"\1 ", s, flags=re.IGNORECASE)
        s = re.sub(r"(\d{1,2})de([a-zA-Z]+)de(\d{4})", r"\1 de \2 de \3", s, flags=re.IGNORECASE)
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        s = re.sub(r"(\d+)([a-zA-Z]{3,})", r"\1 \2", s)
        s = re.sub(r"([€$£¥])([a-zA-Z])", r"\1 \2", s)
        return s

    for line in lines:
        stripped = line.strip()
        if len(stripped) == 1:
            run.append(stripped)
        elif not stripped:
            continue
        else:
            if len(run) >= 3:
                new_lines.append(process_run(run))
            else:
                new_lines.extend(run)
            run = []
            new_lines.append(line)
    if len(run) >= 3:
        new_lines.append(process_run(run))
    else:
        new_lines.extend(run)

    return "\n".join(new_lines)


def _nif(text: str) -> tuple[Any, float]:
    text = _clean_text(text)
    candidates: list[tuple[str, float]] = []
    for m in _NIF_RE.finditer(text):
        raw_val = m.group(1)
        norm_val = normalizers.normalize_nif(raw_val)
        start_pos = m.start()
        preceding = text[max(0, start_pos - 40) : start_pos].lower()
        is_client = "cliente" in preceding or "clernie" in preceding or "cilemar" in preceding
        is_known_client = norm_val in _KNOWN_CLIENT_CIFS

        if is_known_client or is_client:
            score = 0.4
        else:
            score = 0.85 if "nif" in preceding or "cif" in preceding else 0.8
        candidates.append((norm_val, score))

    if not candidates:
        return (None, 0.0)
    # Prefer higher score; on tie, maintain order
    best_val, best_score = max(candidates, key=lambda c: c[1])
    return (best_val, best_score)


def _iban(text: str) -> tuple[Any, float]:
    text = _clean_text(text)
    m_label = re.search(rf"{_IBAN_LABEL_PAT}{_IBAN_RE.pattern}", text, re.IGNORECASE)
    if m_label:
        return (normalizers.normalize_iban(m_label.group(1)), 0.9)
    m = _IBAN_RE.search(text)
    if m:
        return (normalizers.normalize_iban(m.group(1)), 0.9)
    # Fallback: slashed IBAN pattern like ES44/1465/0100/9517/0430/2211 or E544/1465/...
    m_slash = re.search(r"\b((?:ES|E5)\d{2}(?:/\d{4}){5})\b", text, re.IGNORECASE)
    if m_slash:
        return (normalizers.normalize_iban(m_slash.group(1)), 0.9)
    return (None, 0.0)


def _total(text: str) -> tuple[Any, float]:
    text = _clean_text(text)
    m = _TOTAL_RE.search(text)
    return (normalizers.parse_amount(m.group(1)), 0.7) if m else (None, 0.0)


def _base(text: str) -> tuple[Any, float]:
    text = _clean_text(text)
    m = _BASE_RE.search(text)
    if not m:
        m = re.search(r"Importe\s+base\s*:\s*([0-9][\d.,]*)", text, re.IGNORECASE)
    return (normalizers.parse_amount(m.group(1)), 0.6) if m else (None, 0.0)


def _iva_lines(text: str) -> list[str]:
    """Resto de cada línea que menciona IVA (soporta "IVA (21%): 522,90",
    "I.V.A. (21%): 188,60", "Cuota IVA: EUR 413,61", "IVA.......... 181,80", "IVA 21% 522,90",
    "TVA (21%): € 327,60", "MwSt. (21%): € 655,20", "VAT (21%): $ 0.00")."""
    text = _clean_text(text)
    lines: list[str] = []
    for line in text.splitlines():
        # Evitar falsos positivos con identificadores fiscales como "N° TVA: FR..." o "P. IVA: A..."
        if re.search(r"(?:N[°º]\s*TVA|P\.\s*IVA\s*:?\s*[A-Z])", line, re.IGNORECASE):
            continue
        m = _IVA_LINE_RE.search(line)
        if m:
            rest = m.group(1)
            # Si en la misma línea aparece el total después de IVA (ej. texto reensamblado), cortar antes de TOTAL
            rest = re.split(rf"(?<![A-Za-z0-9_-])\b{_TOTAL_LABELS}\b", rest, flags=re.IGNORECASE)[0]
            lines.append(rest)
    return lines


def _line_numbers(line: str) -> list[str]:
    """Números de la línea tras quitar relleno (puntos de guía, EUR...)."""
    # Separate fused percentage/amount like 21%27150 or 21%215.35 -> 21% 27150
    line = re.sub(r"(\d+%\s*)([0-9][\d.,]*)", r"\1 \2", line)
    return [m.group(1) for m in _AMOUNT_RE.finditer(line)]


def _normalize_iva_line(line: str) -> str:
    # Handle OCR mistyped % as K e.g. "IVA 21K 197,02" or " 21K 197,02"
    line = re.sub(r"(?i)(?:\bIVA[-:\s]*)?(\d{1,2})\s*[Kk]\b", r" \1% ", line)
    # Fused rate + '5/' + 5-digit decimal e.g. "IVA215/27150" or "215/27150" -> 21% 271.50
    line = re.sub(r"(?i)(?:\bIVA[-:\s]*)?(\d{1,2})5/(\d{3})(\d{2})\b(?![.,])", r" \1% \2.\3", line)
    # Fused rate + '%' + 5-digit decimal without dot/comma e.g. "IVA21%27150" or "21%27150" -> 21% 271.50
    line = re.sub(r"(?i)(?:\bIVA[-:\s]*)?(\d{1,2})%(\d{3})(\d{2})\b(?![.,])", r" \1% \2.\3", line)
    # Remaining OCR artifacts
    line = re.sub(r"(?i)(?:\bIVA[-:\s]*)?(\d{1,2})5/", r" \1% ", line)
    line = re.sub(r"(?i)\bIVA[-:\s]*(\d{1,2})[5%K/]+", r" \1% ", line)
    line = re.sub(r"^\s*(\d{1,2})[5%K/]+(?:\s*/)?", r" \1% ", line)
    # Separate fused rate and amount without altering already spaced numbers
    line = re.sub(r"(\d+%\s*)([0-9][\d.,]*)", r"\1 \2", line)
    return line


def _iva_rate(text: str) -> tuple[Any, float]:
    for line in _iva_lines(text):
        line_norm = _normalize_iva_line(line)
        m = _RATE_RE.search(line_norm) or _RATE_RE.search(line)
        if m:
            return (int(float(m.group(1).replace(",", "."))), 0.6)
    return (None, 0.0)


def _iva_amount(text: str) -> tuple[Any, float]:
    for line in _iva_lines(text):
        line_norm = _normalize_iva_line(line)
        rate = _RATE_RE.search(line_norm)
        numbers = [n for n in _line_numbers(line_norm) if not rate or n != rate.group(1)]
        if numbers:
            return (normalizers.parse_amount(numbers[-1]), 0.6)
    return (None, 0.0)


def _fecha(text: str) -> tuple[Any, float]:
    text = _clean_text(text)
    # 1. Buscar en líneas con etiqueta de fecha si no es placeholder
    for m in _FECHA_LABEL_RE.finditer(text):
        target = m.group(1).strip()
        if re.match(r"^[_.\s-]+$", target):
            continue
        m_num = _FECHA_NUM_RE.search(target)
        if m_num:
            return (m_num.group(1), 0.7)
        w = _parse_written_date(target)
        if w:
            return (w, 0.7)

    # 2. Fechas escritas / naturales en cualquier parte del texto
    w = _parse_written_date(text)
    if w:
        return (w, 0.6)

    # 3. Fecha numérica en líneas que no sean de condiciones de pago ni placeholders
    for line in text.splitlines():
        if re.search(r"[_\s]{4,}", line) and any(
            k in line.lower() for k in ["fecha", "date", "datum", "data"]
        ):
            continue
        if (
            "condic" in line.lower()
            or "termi" in line.lower()
            or "zahlung" in line.lower()
            or "payment" in line.lower()
        ):
            continue
        m_num = _FECHA_NUM_RE.search(line)
        if m_num:
            return (m_num.group(1), 0.6)

    # Fallback fecha numérica en cualquier sitio
    m_num = _FECHA_NUM_RE.search(text)
    if m_num:
        return (m_num.group(1), 0.6)

    return (None, 0.0)


def _pedido(text: str) -> tuple[Any, float]:
    text = _clean_text(text)
    m = _PEDIDO_RE.search(text)
    if m:
        raw_match = m.group(1).strip()
        # Normalize PO 2026/0478 or PO 2026-0478 or PO-2026-0478 or PO/2026/0478
        m_sub = re.search(
            r"\b([A-Z]{1,2})[\s/-]+(\d{4})[\s/-]+(\d{3,4})\b", raw_match, re.IGNORECASE
        )
        if m_sub:
            norm_val = f"{m_sub.group(1).upper()}-{m_sub.group(2)}-{m_sub.group(3)}"
            return (norm_val, 0.7)
        val = raw_match.upper()
        val = re.split(r"[\s,;:]", val)[0]
        if re.match(r"^[A-Z]{1,2}-[0-9]{4}-[0-9]{3,4}$", val):
            return (val, 0.7)
    m_fall = _FALLBACK_PEDIDO_RE.search(text)
    if m_fall:
        raw_fall = m_fall.group(1).strip()
        m_sub = re.search(
            r"\b([A-Z]{1,2})[\s/-]+(\d{4})[\s/-]+(\d{3,4})\b", raw_fall, re.IGNORECASE
        )
        if m_sub:
            return (f"{m_sub.group(1).upper()}-{m_sub.group(2)}-{m_sub.group(3)}", 0.7)
        return (raw_fall.upper(), 0.7)
    if m:
        val = re.split(r"[\s,;:]", m.group(1).upper())[0]
        return (val, 0.7)
    return (None, 0.0)


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
