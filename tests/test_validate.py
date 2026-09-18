"""T9 — validador de contrato: la misma validación que hará la organización.

Fixtures bajo `.sdd/` (estado de trabajo jamás en /tmp).
"""

import shutil
from pathlib import Path

from albertitos.validate import main as validar_cli
from albertitos.validate import validar


def _sembrar_lote(nombre: str, n: int = 500) -> tuple[Path, Path]:
    base = Path(".sdd") / "pytest-tmp" / nombre
    if base.exists():
        shutil.rmtree(base)
    facturas = base / "facturas"
    facturas.mkdir(parents=True)
    nombres = [f"factura_{i:03d}.pdf" for i in range(n)]
    for nombre_pdf in nombres:
        (facturas / nombre_pdf).write_bytes(b"%PDF-1.4 fixture\n")
    outcomes = base / "outcomes.jsonl"
    outcomes.write_text(
        "".join(f'{{"file_id": "{n}", "result": "PAGAR"}}\n' for n in nombres),
        encoding="utf-8",
    )
    return outcomes, facturas


def _limpiar(base: Path) -> None:
    shutil.rmtree(base.parent)


def test_lote_correcto_500_pasa():
    outcomes, facturas = _sembrar_lote("validate-ok")
    try:
        r = validar(outcomes, facturas)
        assert r["ok"] is True
        assert r["n_validas"] == 500 and r["errores"] == []
        assert validar_cli(["--outcomes", str(outcomes), "--facturas", str(facturas)]) == 0
    finally:
        _limpiar(facturas.parent)


def test_duplicado_falla():
    outcomes, facturas = _sembrar_lote("validate-dup")
    try:
        primera = outcomes.read_text(encoding="utf-8").splitlines()[0]
        with outcomes.open("a", encoding="utf-8") as fh:
            fh.write(primera + "\n")  # línea 501 duplicada
        r = validar(outcomes, facturas)
        assert r["ok"] is False
        motivos = " ".join(e["motivo"] for e in r["errores"])
        assert "duplicado" in motivos
        assert validar_cli(["--outcomes", str(outcomes), "--facturas", str(facturas)]) == 1
    finally:
        _limpiar(facturas.parent)


def test_file_id_normalizado_falla():
    base = Path(".sdd") / "pytest-tmp" / "validate-norm"
    if base.exists():
        shutil.rmtree(base)
    facturas = base / "facturas"
    facturas.mkdir(parents=True)
    # el acento de la 'u': dir usa descompuesta (u + \u0301); la NFKC (ú = \u00fa)
    # NO es el basename exacto → error de normalización
    (facturas / "factu\u0301a_1.pdf").write_bytes(b"%PDF-1.4\n")  # u + acento comb.
    outcomes = base / "outcomes.jsonl"
    outcomes.write_text(
        '{"file_id": "factu\\u0301a_1.pdf", "result": "PAGAR"}\n'  # exacto → válido
        '{"file_id": "fact\\u00faa_1.pdf", "result": "PAGAR"}\n'    # NFKC ≈ igual → ERROR
        '{"file_id": "subdir/factu\\u0301a_1.pdf", "result": "PAGAR"}\n'  # ruta → ERROR
        '{"file_id": "./factu\\u0301a_1.pdf", "result": "PAGAR"}\n'  # ruta → ERROR
        ,
        encoding="utf-8",
    )
    try:
        r = validar(outcomes, facturas)
        assert r["ok"] is False
        motivos = [e["motivo"] for e in r["errores"]]
        assert any("normalizado" in m for m in motivos)
        assert sum("contiene ruta" in m for m in motivos) == 2
    finally:
        shutil.rmtree(base)


def test_file_id_con_mayusculas_falla():
    """Mayúsculas NO son el basename exacto: jamás se normaliza el file_id."""
    base = Path(".sdd") / "pytest-tmp" / "validate-case"
    if base.exists():
        shutil.rmtree(base)
    facturas = base / "facturas"
    facturas.mkdir(parents=True)
    (facturas / "factura_8801.pdf").write_bytes(b"%PDF-1.4\n")
    outcomes = base / "outcomes.jsonl"
    outcomes.write_text(
        '{"file_id": "Factura_8801.PDF", "result": "PAGAR"}\n', encoding="utf-8"
    )
    try:
        r = validar(outcomes, facturas)
        assert r["ok"] is False
        assert any("normalizado" in e["motivo"] for e in r["errores"])
    finally:
        shutil.rmtree(base)


def test_result_invalido_falla():
    outcomes, facturas = _sembrar_lote("validate-result")
    try:
        lineas = outcomes.read_text(encoding="utf-8").splitlines()
        lineas[0] = '{"file_id": "factura_000.pdf", "result": "SI"}'
        outcomes.write_text("\n".join(lineas) + "\n", encoding="utf-8")
        r = validar(outcomes, facturas)
        assert r["ok"] is False
        assert any("result inválido" in e["motivo"] for e in r["errores"])
    finally:
        _limpiar(facturas.parent)


def test_pdf_sin_linea_falla():
    outcomes, facturas = _sembrar_lote("validate-falta")
    try:
        lineas = outcomes.read_text(encoding="utf-8").splitlines()
        outcomes.write_text("\n".join(lineas[:-1]) + "\n", encoding="utf-8")
        r = validar(outcomes, facturas)
        assert r["ok"] is False
        assert any("sin línea" in e["motivo"] for e in r["errores"])
    finally:
        _limpiar(facturas.parent)
