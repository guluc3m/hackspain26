"""Extractores de campos: texto crudo → candidatos (valor, confianza).

Cada campo tiene UNO o MÁS extractores. Todos los candidatos se conservan:
nunca se colapsan en el store (AGENTS.md §2). Los extractores proponen;
las reglas deciden.
"""

from __future__ import annotations

import re

from albertitos.parse.normalizers import (
    normalize_iban,
    normalize_nif,
    parse_amount_float,
    parse_fecha,
    validate_iban,
    validate_nif,
)

# Confianzas por calidad de lectura. Son constantes del parser; los umbrales
# que usan las reglas viven en config (rules/*.yaml).
_CONF_ALTA = 0.9
_CONF_MEDIA = 0.85
_CONF_BAJA = 0.6
_CONF_MALA = 0.4

# Líneas que hablan del CLIENTE, no del proveedor: no de ahí salen NIF/IBAN.
_LINEAS_CLIENTE = re.compile(
    r"cliente|facturar a|destinatario|bill to|cif\b|castellana", re.IGNORECASE
)

_RE_TOKEN = r"([0-9][0-9.,]*)(?:\s*€)?"


def _lineas(texto: str) -> list[str]:
    return [ln.strip() for ln in texto.splitlines() if ln.strip()]


def _lineas_no_cliente(texto: str) -> list[str]:
    return [ln for ln in _lineas(texto) if not _LINEAS_CLIENTE.search(ln)]


# ---------------------------------------------------------------- nif

_RE_NIF = re.compile(
    r"(?:N\.?I\.?F\.?|C\.?I\.?F\.?)\s*[:\-]?\s*([A-Z]-?\d{7,8}|-?\d{8}[A-Z])\b",
    re.IGNORECASE,
)
_RE_NIF_SUELTO = re.compile(r"\b([A-Z]\d{8}|\d{8}[A-Z])\b")
_RE_LINEA_IBAN = re.compile(r"iban|ES\d{2}\s?\d{4}|cuenta de abono", re.IGNORECASE)


def extraer_nif(texto: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for linea in _lineas_no_cliente(texto):
        hay_labeled = False
        for m in _RE_NIF.finditer(linea):
            nif = normalize_nif(m.group(1))
            out.append((nif, _CONF_ALTA if validate_nif(nif) else _CONF_MALA))
            hay_labeled = True
        if hay_labeled or _RE_LINEA_IBAN.search(linea):
            continue
        for m in _RE_NIF_SUELTO.finditer(linea):
            nif = normalize_nif(m.group(1))
            out.append((nif, _CONF_ALTA if validate_nif(nif) else _CONF_MALA))
    return out


# ---------------------------------------------------------------- iban

_RE_IBAN = re.compile(r"\b(ES\d{2}(?:\s?\d{4}){4}\s?\d{1,4})\b")


def extraer_iban(texto: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for linea in _lineas_no_cliente(texto):
        for m in _RE_IBAN.finditer(linea):
            iban = normalize_iban(m.group(1))
            if len(iban) != 24:
                continue
            if validate_iban(iban):
                conf = _CONF_ALTA
            elif re.fullmatch(r"ES\d{22}", iban):
                # Formato plausible pero mod-97 falla: el corpus usa IBANs
                # sintéticos. Es señal de confianza, NO veto (eso es de las
                # reglas, AGENTS.md §4 / T2).
                conf = 0.75
            else:
                conf = _CONF_MALA
            out.append((iban, conf))
    return out


# ---------------------------------------------------------------- fechas


def extraer_fecha(texto: str) -> list[tuple[str, float]]:
    iso = parse_fecha(texto)
    if iso is None:
        return []
    conf = _CONF_ALTA if _RE_FECHA_NUM_SEARCH(texto) else _CONF_MEDIA
    return [(iso, conf)]


def _RE_FECHA_NUM_SEARCH(texto: str) -> bool:
    return re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", texto) is not None


# ---------------------------------------------------------------- pedido

_RE_PEDIDO = re.compile(r"\b(PO-\d{4}-\d{3,5})\b", re.IGNORECASE)


def extraer_pedido(texto: str) -> list[tuple[str, float]]:
    return [(m.group(1).upper(), _CONF_ALTA) for m in _RE_PEDIDO.finditer(texto)]


# ---------------------------------------------------------------- número de factura

_RE_NUM_FACTURA = re.compile(
    r"\b((?:FA|F26|FT)-?\d{3,6}|\d{4}/\d{3,6}|\d{4}-\d{3,6}(?:-[A-Z])?)\b",
    re.IGNORECASE,
)


def extraer_numero_factura(texto: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for linea in texto.splitlines():
        if not re.search(r"factura|invoice", linea, re.IGNORECASE):
            continue
        if re.search(r"total", linea, re.IGNORECASE):
            continue
        for m in _RE_NUM_FACTURA.finditer(linea):
            out.append((m.group(1).upper(), _CONF_ALTA))
    return out


# ---------------------------------------------------------------- importes


def _importe_tras_label(texto: str, label_re: str) -> list[tuple[float, float]]:
    """Importes que siguen a una etiqueta, una vez por línea."""
    out: list[tuple[float, float]] = []
    pat = re.compile(label_re + r"\s*[:.\-]*\s*(?:EUR\s*)?" + _RE_TOKEN, re.IGNORECASE)
    for linea in texto.splitlines():
        m = pat.search(linea)
        if not m:
            continue
        val = parse_amount_float(m.group(1))
        if val is not None:
            out.append((val, _CONF_ALTA))
    return out


_RE_LABEL_BASE = r"(?:base\s*imponible|importe\s*base|subtotal|base)"
_RE_LABEL_IVA = r"(?:cuota\s+i\.?v\.?a\.?|i\.?v\.?a\.?)(?:\s*\(\s*\d{1,2}\s*%?\s*\))?"
_RE_LABEL_TOTAL = r"(?:importe\s*total|total\s*a\s*pagar|total\s*factura|total)"


def extraer_base(texto: str) -> list[tuple[float, float]]:
    return _importe_tras_label(texto, _RE_LABEL_BASE)


def extraer_iva_amount(texto: str) -> list[tuple[float, float]]:
    return _importe_tras_label(texto, _RE_LABEL_IVA)


def extraer_total(texto: str) -> list[tuple[float, float]]:
    # "IMPORTE TOTAL" ya lo cubre "total": deduplicar por valor conservando un
    # candidato por extractor y valor distinto.
    seen: set[float] = set()
    dedup: list[tuple[float, float]] = []
    for v, c in _importe_tras_label(texto, _RE_LABEL_TOTAL):
        if v not in seen:
            seen.add(v)
            dedup.append((v, c))
    return dedup


_RE_IVA_PCT = re.compile(r"i\.?v\.?a\.?\.?\s*\(\s*(\d{1,2})\s*%?\s*\)", re.IGNORECASE)


def extraer_iva_pct(texto: str) -> list[tuple[int, float]]:
    out: list[tuple[int, float]] = []
    for m in _RE_IVA_PCT.finditer(texto):
        pct = int(m.group(1))
        if 0 <= pct <= 100:
            out.append((pct, _CONF_ALTA))
    return out


# ---------------------------------------------------------------- proveedor

_RE_EMPRESA_SUFFIX = re.compile(r"\bS\.?\s?[LAC]\.?\s*$", re.IGNORECASE)
_RE_EMISOR = re.compile(
    r"^Emisor:\s*(.+?)(?:\s*·\s*(?:NIF|Valencia|Sevilla|Málaga|Murcia)|\s*·\s*$|$)",
    re.MULTILINE,
)
_PALABRAS_NO_PROVEEDOR = re.compile(
    r"nif|iban|fecha|pedido|factura|cliente|cif|total|base|iva|documento|emitido",
    re.IGNORECASE,
)


def _proveedor_header(texto: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    for linea in texto.splitlines()[:8]:
        ln = linea.strip()
        if not ln or _PALABRAS_NO_PROVEEDOR.search(ln):
            continue
        if _RE_EMPRESA_SUFFIX.search(ln):
            out.append((ln, _CONF_BAJA))
            break
    return out


def _proveedor_emisor(texto: str) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    m = _RE_EMISOR.search(texto)
    if m:
        nombre = m.group(1).strip().rstrip("· ").strip()
        if nombre:
            out.append((nombre, _CONF_MEDIA))
    return out