"""Emisión de outcomes.jsonl + validador de contrato de entrega.

Contrato (AGENTS.md §1): una línea por factura —
  {"file_id": "<nombre EXACTO del PDF>", "result": "PAGAR"|"NO_PAGAR"|"ESCALAR"}
+ campos de traza opcionales. `file_id` jamás normalizado ni con ruta.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from albertitos.store import Store

_RESULTADOS_VALIDOS = ("PAGAR", "NO_PAGAR", "ESCALAR")


def emit_outcomes(store: Store, out_path: str | Path,
                  only_files: set[str] | None = None) -> Path:
    """Escribe outcomes.jsonl desde el store, ordenado por file_id.

    `only_files` (T21): si se da, emite SOLO esos file_id — así el lote 2
    produce `outcomes_lote2.jsonl` (40 líneas) SIN tocar ni mezclar el lote 1
    cuando ambos conviven en el mismo store. None ⇒ todo el store.
    Determinista: mismo contenido ⇒ mismo fichero byte a byte.
    """
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    decisions = store.all_decisions()
    if only_files is not None:
        decisions = [d for d in decisions if d.file_id in only_files]
    lines = []
    for d in sorted(decisions, key=lambda x: x.file_id):
        obj = {
            "file_id": d.file_id,
            "result": d.result,
            "rule_ids": d.rule_codes,
            "invoice_id": d.invoice_id,
            "engine_version": d.engine_version,
            "config_version": d.config_version,
        }
        lines.append(json.dumps(obj, ensure_ascii=False, sort_keys=False))
    out.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return out


def read_outcomes(path: str | Path) -> list[dict]:
    out: list[dict] = []
    for i, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(),
                             start=1):
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise ValueError(f"outcomes.jsonl línea {i} no es JSON válido: {e}")
    return out


def validate_outcomes(path: str | Path, pdf_dir: str | Path) -> list[str]:
    """Validador de contrato: file_id exactos y únicos de pdf_dir, resultados
    válidos. Devuelve la lista de errores (vacía si el contrato se cumple)."""
    errors: list[str] = []
    entries = read_outcomes(path)
    expected = sorted(p.name for p in Path(pdf_dir).glob("*.pdf"))
    file_ids = [e.get("file_id") for e in entries]
    if len(set(file_ids)) != len(file_ids):
        errors.append("file_id duplicados en outcomes.jsonl")
    for e in entries:
        fid = e.get("file_id", "")
        if "/" in fid or "\\" in fid or fid != fid.strip() or fid == "":
            errors.append(f"file_id no es un nombre exacto: {fid!r}")
        if e.get("result") not in _RESULTADOS_VALIDOS:
            errors.append(f"result inválido para {fid}: {e.get('result')!r}")
    missing = sorted(set(expected) - set(file_ids))
    extra = sorted(set(file_ids) - set(expected))
    if missing:
        errors.append(f"faltan {len(missing)} file_id (p. ej. {missing[:3]})")
    if extra:
        errors.append(f"sobran {len(extra)} file_id (p. ej. {extra[:5]})")
    return errors


_RE_PDF_NAME = re.compile(r".*\.pdf$", re.IGNORECASE)


def list_pdf_files(pdf_dir: str | Path) -> list[Path]:
    """PDFs del directorio, ordenados por nombre EXACTO (determinismo)."""
    return sorted(
        (p for p in Path(pdf_dir).iterdir() if p.is_file()
         and _RE_PDF_NAME.search(p.name)),
        key=lambda p: p.name,
    )