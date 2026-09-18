#!/usr/bin/env python3
"""Estrategia OCR escalonada para las facturas de la Caja.

Escalera:
  1. pdftotext  -> texto embebido (471/500 casos)
  2. rasterizar -> tesseract -l spa (29 scans)
  3. confianza baja o campo clave perdido -> flag para ESCALAR / revision

Salida: ocr_out/<file>.json + resumen en stdout.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ---------- tunables ----------
DPI = 200                 # 150 ok, 300 marginal-mejor; 200 equilibrio
MIN_CHARS = 50            # menos que esto => sin texto embebido
TESS_LANG = "spa"
MIN_CONF = 55             # confianza media tesseract (0-100)
WORKERS = 12              # 20 cores, IO/CPU mixto

# ---------- regex de campos (tolerantes al ruido de OCR) ----------
RE_NUM = re.compile(
    r"(?:FACTURA\s*(?:SIMPLIFICADA)?\s*(?:N[°º*#]|num|ref)?\s*[:.]?\s*|(?:Invoice|#|REF\s+FACTURA)\s*[:#]?\s*)"
    r"([A-Z0-9]{2,4}[-/ ]?\d{3,6}(?:[/-]\d{2,6})?)", re.I)
RE_FECHA = re.compile(r"(\d{1,2})[/\-. ](\d{1,2})[/\-. ](\d{4})")
MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
         "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
         "noviembre": 11, "diciembre": 12}
RE_FECHA_MES = re.compile(r"(\d{1,2})\s+de\s+([a-zñáéíóú]+)\s+de\s+(\d{4})", re.I)
RE_PO = re.compile(r"P[OE][\s\-:.]*?(\d{4})[\s\-:.]?(\d{2,6})", re.I)
RE_TOTAL = re.compile(r"TOTAL[^\n\d]*?([\d][\d .,]*\d)", re.I)
RE_IBAN = re.compile(r"\b([A-Z]{2}\d{2})(?:\s?\d{4}){4,5}\s?\d{1,4}\b")
RE_NIF = re.compile(r"\b([A-HJ-NP-SUV]\d{7,8}[A-Z0-9]?)\b")
RE_IVA = re.compile(r"I\.?\s?V\.?\s?A\.?[^\d%\n]{0,15}(\d{1,2})\s?%", re.I)
RE_NUM_FB = re.compile(r"\b((?:FA|F26)[-/ ]?\d{3,5}|2026/\d{4,6}|FAB?\d{3,4})\b")
ZW = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)

def _norm_num(s: str) -> str:
    """'2.489,99' / '2.967,25' / '61269' / '1.135.20' (OCR) -> '2967.25' etc."""
    s = s.translate(ZW).replace(" ", "").replace("\u00a0", "")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):   # español 1.234,56
            s = s.replace(".", "").replace(",", ".")
        else:                             # inglés 1,234.56
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1:
        # OCR que pega miles con punto y decimales con punto: '1.135.20'
        partes = s.split(".")
        s = "".join(partes[:-1]) + "." + partes[-1]
    return s

def extract_fields(text: str) -> dict:
    campos = {}
    m = RE_NUM.search(text)
    num = m.group(1).replace(" ", "").upper() if m else None
    if not num:  # fallback para OCR con etiqueta ilegible
        fb = RE_NUM_FB.search(text)
        num = fb.group(1).replace(" ", "").upper() if fb else None
    campos["num_factura"] = num
    m = RE_FECHA.search(text)
    if m:
        try:
            dd, mm, aa = int(m.group(1)), int(m.group(2)), int(m.group(3))
            # guarda anti-OCR: anhos corruptos (2076, 7900...) se descartan
            if 1 <= mm <= 12 and 1 <= dd <= 31 and 2020 <= aa <= 2027:
                campos["fecha"] = f"{aa:04d}-{mm:02d}-{dd:02d}"
        except ValueError:
            pass
    if not campos.get("fecha"):
        m = RE_FECHA_MES.search(text)
        if m and m.group(2).lower() in MESES:
            campos["fecha"] = f"{int(m.group(3)):04d}-{MESES[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = RE_PO.search(text)
    if m:
        campos["pedido"] = f"PO-{m.group(1)}-{m.group(2)}"
    m = RE_TOTAL.search(text)
    if m:
        total = _norm_num(m.group(1))
        # guarda anti-OCR: entero sospechosamente largo -> coma decimal perdida
        # (Caja: totales ~50-9500; "61269" son 612,69)
        if "." not in total and len(total.split(".")[0]) > 4:
            total = total[:-2] + "." + total[-2:]
        campos["total"] = total
    m = RE_IVA.search(text)
    if m:
        campos["iva_pct"] = int(m.group(1))
    nifs = RE_NIF.findall(text)
    campos["nif"] = nifs[0] if nifs else None
    return campos

def conf_ocr(pdf: Path) -> float:
    try:
        out = subprocess.run(["tesseract", str(pdf.with_suffix(".png")), "-", "-l", TESS_LANG, "--psm", "6", "tsv"],
                             capture_output=True, text=True, timeout=60).stdout
        confs = [float(r.split("\t")[-2]) for r in out.splitlines()[1:]
                 if len(r.split("\t")) > 11 and r.split("\t")[-2].replace(".","",1).replace("-","",1).isdigit()
                 and r.split("\t")[-1].strip()]
        return sum(confs) / len(confs) if confs else 0.0
    except Exception:
        return 0.0

def procesar(pdf: Path, out_dir: Path) -> dict:
    res = {"file_id": pdf.name, "origen": None, "ocr_conf": None, "campos": {}, "avisos": []}
    # --- nivel 1: texto embebido ---
    t = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    # limpieza de caracteres invisibles (algunos PDFs intercalan U+200B en las cifras)
    t = t.translate(ZW)
    if len(t.strip()) >= MIN_CHARS:
        res["origen"] = "texto"
        res["campos"] = extract_fields(t)
    else:
        png = pdf.with_suffix(".png")
        for dpi in (DPI, 300):            # 2º pase a más resolución si el 1º flojea
            try:
                subprocess.run(["pdftoppm", "-r", str(dpi), "-png", "-singlefile", str(pdf), str(png.with_suffix(""))],
                               check=True, timeout=60, capture_output=True)
            except subprocess.SubprocessError as e:
                res["avisos"].append(f"rasterizado_fallo({dpi}): {e}")
            try:
                t = subprocess.run(["tesseract", str(png), "-", "-l", TESS_LANG, "--psm", "6"],
                                   capture_output=True, text=True, timeout=60).stdout
            except FileNotFoundError:
                res["avisos"].append("tesseract_no_disponible"); t = ""
            t = t.translate(ZW)
            campos = extract_fields(t)
            res["ocr_conf"] = round(conf_ocr(png), 1)
            if res["origen"] is None:
                res["origen"], res["campos"] = "ocr", campos
            elif sum(v is not None for v in campos.values()) > sum(v is not None for v in res["campos"].values()):
                res["campos"] = campos
            if all(res["campos"].get(k) for k in ("num_factura", "fecha", "pedido", "total")):
                break
        png.unlink(missing_ok=True)

    c = res["campos"]
    # --- nivel 3: juicio de calidad ---
    claves = ["num_factura", "fecha", "pedido", "total"]
    faltan = [k for k in claves if not c.get(k)]
    if res["origen"] == "ocr":
        if (res["ocr_conf"] or 0) < MIN_CONF:
            res["avisos"].append(f"conf_baja({res['ocr_conf']})")
        if len(faltan) >= 2:
            res["avisos"].append("campos_criticos_perdidos")
    if faltan and res["origen"] == "texto":
        res["avisos"].append("campos_faltan_en_texto")
    return res

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=".", help="directorio con PDFs")
    ap.add_argument("--out", default="ocr_out", help="directorio de salida JSON")
    ap.add_argument("--solo-scans", action="store_true", help="solo PDFs sin texto embebido")
    args = ap.parse_args()

    src = Path(args.dir); out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(src.glob("*.pdf"))
    if args.solo_scans:
        pdfs = [p for p in pdfs if len(subprocess.run(["pdftotext", str(p), "-"],
                 capture_output=True, text=True).stdout.strip()) < MIN_CHARS]
    print(f"{len(pdfs)} PDFs a procesar, {WORKERS} workers", file=sys.stderr)

    with ThreadPoolExecutor(WORKERS) as ex:
        for res in ex.map(lambda p: procesar(p, out), pdfs):
            (out / (res["file_id"] + ".json")).write_text(
                json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")

    # resumen
    docs = [json.load(open(out / (p.name + ".json"))) for p in pdfs]
    from collections import Counter
    print(Counter(d["origen"] for d in docs))
    sin_campos = [d["file_id"] for d in docs
                  if any(not d["campos"].get(k) for k in ("num_factura", "fecha", "pedido", "total"))]
    print(f"con campo clave perdido: {len(sin_campos)}")
    for f in sin_campos[:30]: print("  -", f)
    bajas = [d["file_id"] for d in docs if d.get("ocr_conf") is not None and d["ocr_conf"] < MIN_CONF]
    print(f"confianza OCR < {MIN_CONF}: {len(bajas)}"); 
    for f in bajas: print("  !", f)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
