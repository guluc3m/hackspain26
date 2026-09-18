"""Validador de contrato de `outcomes.jsonl` (T9).

Es la MISMA validación que la organización hará contra su referencia privada:
    python -m albertitos.validate --outcomes outcomes.jsonl --facturas DIR

Comprueba, con exit 0/1 y reporte de diferencias:
  1. una línea por PDF exacto del directorio (ni una de menos ni de más);
  2. `file_id` = basename EXACTO: sin ruta, sin normalizar (se detecta la
     variante normalizada — NFKC, mayúsculas, espacios — y se marca error);
  3. sin duplicados;
  4. `result` ∈ {PAGAR, NO_PAGAR, ESCALAR}.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any

RESULTADOS_VALIDOS = ("PAGAR", "NO_PAGAR", "ESCALAR")


def _variantes_normalizadas(file_id: str, pdfs: set[str]) -> set[str]:
    """PDFs reales cuyo nombre normalizado (NFKC/casefold/strip) coincide con
    el file_id dado — delata un file_id normalizado en lugar del exacto."""
    objetivo = unicodedata.normalize("NFKC", file_id).casefold().strip()
    variantes = set()
    for pdf in pdfs:
        if pdf == file_id:
            continue
        if unicodedata.normalize("NFKC", pdf).casefold().strip() == objetivo:
            variantes.add(pdf)
    return variantes


def validar(outcomes_path: Path, facturas_dir: Path) -> dict[str, Any]:
    """Valida el JSONL contra los PDFs del directorio. Devuelve un reporte
    {ok, n_lineas, n_facturas, errores: [{linea, file_id, motivo}]}."""
    errores: list[dict[str, Any]] = []

    pdfs = {p.name for p in Path(facturas_dir).glob("*.pdf")} if Path(facturas_dir).is_dir() else set()
    if not pdfs:
        errores.append({"linea": 0, "file_id": "", "motivo": f"sin PDFs en {facturas_dir}"})

    entradas: list[tuple[int, dict[str, Any]]] = []
    if not Path(outcomes_path).is_file():
        errores.append({"linea": 0, "file_id": "", "motivo": f"no existe {outcomes_path}"})
    else:
        with Path(outcomes_path).open("r", encoding="utf-8") as fh:
            for num, linea in enumerate(fh, start=1):
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    obj = json.loads(linea)
                except json.JSONDecodeError:
                    errores.append({"linea": num, "file_id": "", "motivo": "línea no es JSON válido"})
                    continue
                if not isinstance(obj, dict):
                    errores.append({"linea": num, "file_id": "", "motivo": "la línea no es un objeto"})
                    continue
                entradas.append((num, obj))

    vistos: dict[str, int] = {}
    file_ids_validos: set[str] = set()
    for num, obj in entradas:
        file_id = obj.get("file_id")
        result = obj.get("result")

        if not isinstance(file_id, str) or not file_id:
            errores.append({"linea": num, "file_id": repr(file_id), "motivo": "file_id ausente o no textual"})
            continue
        if "/" in file_id or "\\" in file_id:
            errores.append({"linea": num, "file_id": file_id, "motivo": "file_id contiene ruta"})
            continue

        # ¿variantes normalizadas de un nombre real? ⇒ error (jamás normalizar)
        variantes = _variantes_normalizadas(file_id, pdfs) if file_id not in pdfs else set()
        if file_id not in pdfs:
            if variantes:
                errores.append(
                    {
                        "linea": num,
                        "file_id": file_id,
                        "motivo": f"file_id normalizado; el PDF exacto es {min(variantes)}",
                    }
                )
            else:
                errores.append(
                    {"linea": num, "file_id": file_id, "motivo": "no corresponde a ningún PDF del lote"}
                )
            continue

        if file_id in vistos:
            errores.append(
                {
                    "linea": num,
                    "file_id": file_id,
                    "motivo": f"duplicado (primera aparición en línea {vistos[file_id]})",
                }
            )
            continue
        vistos[file_id] = num
        file_ids_validos.add(file_id)

        if result not in RESULTADOS_VALIDOS:
            errores.append(
                {
                    "linea": num,
                    "file_id": file_id,
                    "motivo": f"result inválido: {result!r} (debe ser PAGAR|NO_PAGAR|ESCALAR)",
                }
            )

    for pdf in sorted(pdfs - file_ids_validos):
        errores.append({"linea": 0, "file_id": pdf, "motivo": "PDF sin línea en outcomes.jsonl"})

    return {
        "ok": not errores,
        "n_lineas": len(entradas),
        "n_facturas": len(pdfs),
        "n_validas": len(file_ids_validos),
        "errores": errores,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m albertitos.validate",
        description="Validador de contrato de outcomes.jsonl contra el lote de facturas.",
    )
    parser.add_argument("--outcomes", default="outcomes.jsonl", help="ruta al outcomes.jsonl")
    parser.add_argument("--facturas", default="caja-de-alberto/facturas", help="directorio con los PDF")
    args = parser.parse_args(argv)
    reporte = validar(Path(args.outcomes), Path(args.facturas))
    if reporte["ok"]:
        print(
            f"OK: {reporte['n_validas']}/{reporte['n_facturas']} facturas válidas, "
            f"sin duplicados, results dentro del contrato."
        )
        return 0
    print(f"FALLA: {len(reporte['errores'])} diferencias encontradas:")
    for e in reporte["errores"]:
        linea = f"línea {e['linea']}" if e["linea"] else "global"
        print(f"  [{linea}] {e['file_id'] or '(sin file_id)'}: {e['motivo']}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
