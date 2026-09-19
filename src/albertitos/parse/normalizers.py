"""Normalización española: importes, fechas, NIF e IBAN.

Los normalizadores NO vetan: devuelven el valor normalizado y quien llama
decide la confianza. Vetar es cosa de las reglas (AGENTS.md §4).
"""

from __future__ import annotations

import datetime
import re
from decimal import Decimal, InvalidOperation

# ---------------------------------------------------------------- importes


def parse_amount(token: str) -> Decimal | None:
    """Convierte un importe en texto a Decimal.

    Formato español: `1.234,56` (punto de miles, coma decimal). También acepta
    el formato anglosajón `1700.00` y enteros `84700`. Devuelve None si el
    token no es un importe plausible.
    """
    s = token.strip().rstrip("€").strip()
    if not s or not re.fullmatch(r"\d+(?:[.,]\d+)*", s):
        return None
    try:
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                miles, dec = ".", ","
            else:
                miles, dec = ",", "."
        elif "," in s:
            if len(s.rsplit(",", 1)[1]) in (1, 2):
                miles, dec = "", ","
            else:
                miles, dec = ",", ""  # T38-F3: coma de MILES ("12,345"), no decimal
        elif "." in s:
            parts = s.split(".")
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]) and len(parts[-1]) == 3:
                miles, dec = ".", ""
            elif len(parts[-1]) in (1, 2):
                miles, dec = "", "."
            else:
                miles, dec = ".", ""
        else:
            miles, dec = "", ""
        clean = s
        if miles:
            clean = clean.replace(miles, "")
        if dec and dec in clean:
            clean = clean.replace(dec, ".")
        return Decimal(clean)
    except InvalidOperation:
        return None


def parse_amount_float(token: str) -> float | None:
    """Decimal normalizado a float con 2 decimales (para candidatos)."""
    d = parse_amount(token)
    if d is None:
        return None
    return float(d.quantize(Decimal("0.01")))


# ---------------------------------------------------------------- fechas

_MESES = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}

_RE_FECHA_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_RE_FECHA_TEXTO = re.compile(
    r"\b(\d{1,2})\s+de\s+([a-záéíóúñ]+)\s+de\s+(\d{4})\b", re.IGNORECASE
)


def parse_fecha(texto: str) -> str | None:
    """Extrae la primera fecha VÁLIDA del texto y la devuelve ISO YYYY-MM-DD.

    T38-F4: una fecha imposible (30/02/2026) NO anula el campo — se itera
    hasta la primera válida (las imposibles son ruido de tipografía)."""
    for m in _RE_FECHA_NUM.finditer(texto):
        d, mm, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            datetime.date(y, mm, d)
            return f"{y:04d}-{mm:02d}-{d:02d}"
        except ValueError:
            continue
    for m in _RE_FECHA_TEXTO.finditer(texto):
        d, mes, y = int(m.group(1)), _MESES.get(m.group(2).lower(), 0), int(m.group(3))
        if not mes:
            continue
        try:
            datetime.date(y, mes, d)
            return f"{y:04d}-{mes:02d}-{d:02d}"
        except ValueError:
            continue
    return None


def fecha_valida(iso: str) -> bool:
    """Un ISO YYYY-MM-DD es una fecha real."""
    try:
        datetime.date.fromisoformat(iso)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------- NIF

_LETRAS_CONTROL = "TRWAGMYFPDXBNJZSQVHLCKE"


def normalize_nif(nif: str) -> str:
    return nif.upper().replace("-", "").replace(" ", "")


def validate_nif(nif: str) -> bool:
    """Formato NIF español. Empresas (letra + 8): sin dígito de control estándar.
    Personas físicas (8 dígitos + letra): letra de control mod 23."""
    n = normalize_nif(nif)
    if re.fullmatch(r"\d{8}[A-Z]", n):
        return _LETRAS_CONTROL[int(n[:8]) % 23] == n[8]
    # Empresas: letra + 8 dígitos (sin dígito de control estandarizado) o
    # formato antiguo letra + 7 dígitos + letra de control.
    return bool(re.fullmatch(r"[ABCDEFGHJNPQRSUVNW]\d{8}", n)) or bool(
        re.fullmatch(r"[ABCDEFGHJNPQRSUVNW]\d{7}[A-Z]", n)
    )


# ---------------------------------------------------------------- IBAN


def normalize_iban(iban: str) -> str:
    return iban.upper().replace(" ", "").replace("-", "")


def validate_iban(iban: str) -> bool:
    """Validación mod-97 (ISO 13616)."""
    s = normalize_iban(iban)
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", s):
        return False
    rearranged = s[4:] + s[:4]
    num = "".join(str(int(c, 36)) for c in rearranged)
    return int(num) % 97 == 1