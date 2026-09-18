"""T12 — script de staging del repo de entrega (subprocess, bash estricto).

Fixtures bajo `.sdd/` (jamás /tmp). El script valida con
`python -m albertitos.validate` antes de copiar y produce EXACTAMENTE
outcomes.jsonl, outcomes_lote2.jsonl, albertitos_plan.pdf.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
ENTREGABLES = {"albertitos_plan.pdf", "outcomes.jsonl", "outcomes_lote2.jsonl"}


@pytest.fixture()
def escenario() -> tuple[Path, dict[str, Path]]:
    """Lote 1 (3 PDFs) + lote 2 (2 PDFs) + outcomes válidos + plan PDF."""
    base = Path(".sdd") / "pytest-tmp" / "stage"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)

    def lote(nombre: str, n: int) -> tuple[Path, Path]:
        facturas = base / nombre
        facturas.mkdir()
        src = FIXTURES / "facturas"
        nombres = sorted(p.name for p in src.glob("*.pdf"))[:n]
        for nombre_pdf in nombres:
            shutil.copy(src / nombre_pdf, facturas / nombre_pdf)
        outcomes = base / f"outcomes_{nombre}.jsonl"
        outcomes.write_text(
            "".join(f'{{"file_id": "{x}", "result": "PAGAR"}}\n' for x in nombres),
            encoding="utf-8",
        )
        return facturas, outcomes

    f1, o1 = lote("facturas-lote1", 3)
    f2, o2 = lote("facturas-lote2", 2)
    plan = base / "plan.pdf"
    shutil.copy(FIXTURES / "2026-01-08_P001.pdf", plan)
    rutas = {
        "OUTCOMES_LOTE1": o1,
        "OUTCOMES_LOTE2": o2,
        "PLAN_PDF": plan,
        "FACTURAS_LOTE1": f1,
        "FACTURAS_LOTE2": f2,
        "DESTINO": base / "delivery-repo",
    }
    yield base, rutas
    shutil.rmtree(base)


def _correr(rutas: dict[str, Path]) -> subprocess.CompletedProcess:
    env = {**os.environ, **{k: str(v) for k, v in rutas.items()}}
    return subprocess.run(
        ["bash", "scripts/stage_delivery.sh"],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )


def _contenidos(destino: Path) -> list[str]:
    return sorted(p.name for p in destino.iterdir() if p.name != ".git")


def test_staging_happy_path_idempotente(escenario):
    _, rutas = escenario
    destino = rutas["DESTINO"]
    r = _correr(rutas)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _contenidos(destino) == sorted(ENTREGABLES)
    assert (destino / "outcomes.jsonl").read_bytes() == rutas["OUTCOMES_LOTE1"].read_bytes()

    # idempotente: segunda ejecución, mismo resultado y sin commit duplicado
    r2 = _correr(rutas)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert _contenidos(destino) == sorted(ENTREGABLES)
    log = subprocess.run(
        ["git", "-C", str(destino), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    assert log.stdout.strip() == "1"

    # cambio de contenidos ⇒ nuevo commit (el staging refleja la realidad)
    nombres = sorted(p.name for p in rutas["FACTURAS_LOTE1"].glob("*.pdf"))
    lineas = [
        f'{{"file_id": "{x}", "result": "{"NO_PAGAR" if i == 0 else "PAGAR"}"}}'
        for i, x in enumerate(nombres)
    ]
    rutas["OUTCOMES_LOTE1"].write_text("\n".join(lineas) + "\n", encoding="utf-8")
    r3 = _correr(rutas)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    log3 = subprocess.run(
        ["git", "-C", str(destino), "rev-list", "--count", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    assert log3.stdout.strip() == "2"


def test_staging_falla_limpio_sin_outcomes(escenario):
    _, rutas = escenario
    rutas["OUTCOMES_LOTE1"].unlink()
    r = _correr(rutas)
    assert r.returncode == 1
    assert "falta el artefacto" in r.stderr
    assert not rutas["DESTINO"].exists() or not any(rutas["DESTINO"].iterdir())


def test_staging_falla_con_duplicado(escenario):
    _, rutas = escenario
    primera = rutas["OUTCOMES_LOTE1"].read_text(encoding="utf-8").splitlines()[0]
    with rutas["OUTCOMES_LOTE1"].open("a", encoding="utf-8") as fh:
        fh.write(primera + "\n")
    r = _correr(rutas)
    assert r.returncode == 1
    assert "duplicado" in (r.stdout + r.stderr)
    assert not rutas["DESTINO"].exists()


def test_staging_falla_con_result_invalido(escenario):
    _, rutas = escenario
    rutas["OUTCOMES_LOTE2"].write_text(
        '{"file_id": "invoice_catering_fa8496.pdf", "result": "SI"}\n',
        encoding="utf-8",
    )
    r = _correr(rutas)
    assert r.returncode == 1
    assert "result inválido" in (r.stdout + r.stderr)


def test_staging_falla_con_secreto(escenario):
    _, rutas = escenario
    with rutas["OUTCOMES_LOTE2"].open("a", encoding="utf-8") as fh:
        fh.write('{"file_id": "x", "result": "PAGAR", "nota": "apiKey=sk-abc123"}\n')
    r = _correr(rutas)
    assert r.returncode == 1
    assert "secreto" in r.stderr


def test_staging_falla_con_file_id_de_otro_lote(escenario):
    """Un JSONL del lote 2 que cite PDFs del lote 1 falla (directorios distintos)."""
    _, rutas = escenario
    rutas["OUTCOMES_LOTE2"].write_text(
        '{"file_id": "invoice_mensajeria_fa7399.pdf", "result": "PAGAR"}\n',
        encoding="utf-8",
    )
    r = _correr(rutas)
    assert r.returncode == 1
    assert "no pasa el validador" in (r.stdout + r.stderr)
