"""Tests de T38-ID1: «llegó el lote 2» en un comando (scripts/lote2_llego.sh).

El script se ejecuta de verdad (bash) contra fixtures pequeños; TODO el
estado vive bajo .sdd (jamás /tmp). Contrato clave: outcomes.jsonl del lote 1
queda byte a byte intacto (hash antes/después).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "lote2_llego.sh"
TMP = REPO / ".sdd" / "pytest-tmp" / "lote2llego"
FIX_FACTURAS = REPO / "tests" / "fixtures" / "facturas"
FIX_LOTE10 = REPO / "tests" / "fixtures" / "lote10"


def _limpiar() -> None:
    if TMP.exists():
        shutil.rmtree(TMP)
    TMP.mkdir(parents=True)


def _lote1() -> tuple[Path, Path]:
    """Directorio lote 1 con 3 PDFs + outcomes.jsonl válido (todo ESCALAR)."""
    pdfs = TMP / "lote1"
    pdfs.mkdir()
    for f in sorted(FIX_FACTURAS.glob("*.pdf")):
        shutil.copy(f, pdfs / f.name)
    out = TMP / "outcomes.jsonl"
    lineas = [
        f'{{"file_id": "{p.name}", "result": "ESCALAR"}}'
        for p in sorted(pdfs.glob("*.pdf"))
    ]
    out.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return pdfs, out


def _lote2(n: int = 2) -> Path:
    d = TMP / "lote2"
    d.mkdir()
    for f in sorted(FIX_LOTE10.glob("*.pdf"))[:n]:
        shutil.copy(f, d / f.name)
    return d


def _env(lote1_pdfs: Path, out1: Path) -> dict[str, str]:
    uv = shutil.which("uv") or "/usr/local/bin/uv"
    return {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHON": f"{uv} run python",
        "ESPERADOS_LOTE2": "2",
        "FACTURAS_LOTE1": str(lote1_pdfs),
        "OUTCOMES_LOTE1": str(out1),
        "OUTCOMES_LOTE2": str(TMP / "outcomes_lote2.jsonl"),
        "STORE_ROOT_LOTE2": str(TMP / "sdd-lote2"),
        "MAESTRO": str(REPO / "tests" / "fixtures" / "maestro_fixture.xlsx"),
        "PLAN_PDF": str(min(FIX_FACTURAS.glob("*.pdf"))),
        "DESTINO": str(TMP / "delivery"),
    }


def _run(lote2: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SCRIPT), str(lote2)],
        cwd=REPO, env=env, check=False, capture_output=True, text=True,
        timeout=300,
    )


def test_lote2_ingesta_validacion_staging_y_lote1_intacto():
    _limpiar()
    pdfs1, out1 = _lote1()
    sha_antes = hashlib.sha256(out1.read_bytes()).hexdigest()
    lote2 = _lote2(n=2)

    r = _run(lote2, _env(pdfs1, out1))
    assert r.returncode == 0, r.stderr

    # lote 2: 0→2 líneas, file_id = basename EXACTO de cada PDF
    contenido = (TMP / "outcomes_lote2.jsonl").read_text().splitlines()
    assert len(contenido) == 2
    nombres = {p.name for p in lote2.glob("*.pdf")}
    assert all(any(n in linea for linea in contenido) for n in nombres)

    # lote 1 INTACTO: outcomes.jsonl byte a byte
    assert hashlib.sha256(out1.read_bytes()).hexdigest() == sha_antes

    # staging: repo con EXACTAMENTE los 3 entregables
    dest = TMP / "delivery"
    entregables = sorted(
        p.name for p in dest.iterdir() if p.name != ".git"
    )
    assert entregables == [
        "albertitos_plan.pdf", "outcomes.jsonl", "outcomes_lote2.jsonl"
    ]

    # resumen legible en español
    assert "Lote 2 listo" in r.stdout


def test_solapado_con_lote1_falla_limpio_sin_ingestar():
    _limpiar()
    pdfs1, out1 = _lote1()
    lote2 = TMP / "lote2-dup"
    lote2.mkdir()
    # cuenta CORRECTA (3 = ESPERADOS 3) pero con un file_id repetido del
    # lote 1 ⇒ debe fallar por SOBREPOSICIÓN, no por cuenta
    for f in sorted(FIX_LOTE10.glob("*.pdf"))[:2]:
        shutil.copy(f, lote2 / f.name)
    repetido = min(pdfs1.glob("*.pdf"))
    shutil.copy(repetido, lote2 / repetido.name)

    env = _env(pdfs1, out1)
    env["ESPERADOS_LOTE2"] = "3"
    r = _run(lote2, env)
    assert r.returncode != 0, r.stdout
    assert "sobreposición" in (r.stderr + r.stdout)
    assert not (TMP / "outcomes_lote2.jsonl").exists()
    # staging NO se ha ejecutado
    assert not (TMP / "delivery").exists()


def test_pdf_repetido_del_lote1_falla_por_solapacion():
    _limpiar()
    pdfs1, out1 = _lote1()
    lote2 = TMP / "lote2-dup"
    lote2.mkdir()
    # 2 PDFs del lote 10 (cuenta correcta) + 1 copiado del lote 1 ⇒ 3 ≠ 2
    # falla por cuenta; para pillar el fence de SOLAPACIÓN usamos
    # ESPERADOS_LOTE2=3 con un repetido del lote 1.
    for f in sorted(FIX_LOTE10.glob("*.pdf"))[:2]:
        shutil.copy(f, lote2 / f.name)
    repetido = min(pdfs1.glob("*.pdf"))
    shutil.copy(repetido, lote2 / repetido.name)

    env = _env(pdfs1, out1)
    env["ESPERADOS_LOTE2"] = "3"
    r = _run(lote2, env)
    assert r.returncode != 0, r.stdout
    assert "sobreposición" in (r.stderr + r.stdout)
    assert not (TMP / "outcomes_lote2.jsonl").exists()


def test_cuenta_incorrecta_falla_limpio():
    _limpiar()
    pdfs1, out1 = _lote1()
    lote2 = _lote2(n=1)  # 1 PDF, se esperaban 2
    r = _run(lote2, _env(pdfs1, out1))
    assert r.returncode != 0
    assert "se esperaban 2" in (r.stderr + r.stdout)
    assert not (TMP / "outcomes_lote2.jsonl").exists()