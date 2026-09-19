"""Tests de T19: staging del repo de entrega (scripts/stage_delivery.sh).

El script se ejecuta de verdad (bash) contra fixtures pequeños; el DESTINO
vive bajo .sdd (estado de trabajo jamás en /tmp).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "stage_delivery.sh"
STAGE_TMP = REPO / ".sdd" / "pytest-tmp" / "stage"


def _limpiar() -> None:
    if STAGE_TMP.exists():
        shutil.rmtree(STAGE_TMP)
    STAGE_TMP.mkdir(parents=True)


def _pdf_dir(destino: str) -> Path:
    """Directorio de facturas con 2 PDFs de verdad (fixtures del corpus)."""
    d = STAGE_TMP / f"facturas-{destino}"
    d.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(sorted((REPO / "tests/fixtures/facturas").glob("*.pdf"))[:2]):
        shutil.copy(f, d / f.name)
    return d


def _outcomes_validos(pdfs: Path, destino: str) -> Path:
    """outcomes.jsonl que pasa el validador de contrato para esos 2 PDFs."""
    out = STAGE_TMP / f"outcomes-{destino}.jsonl"
    lineas = [
        f'{{"file_id": "{p.name}", "result": "ESCALAR"}}'
        for p in sorted(pdfs.glob("*.pdf"))
    ]
    out.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return out


def _run(env_extra: dict[str, str]) -> subprocess.CompletedProcess:
    import shutil

    uv = shutil.which("uv") or "/usr/local/bin/uv"
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "PYTHON": f"{uv} run python",
    }
    env.update(env_extra)
    return subprocess.run(
        ["bash", str(SCRIPT)],
        cwd=REPO, env=env, check=False, capture_output=True, text=True, timeout=120,
    )


def _entorno(destino: str) -> dict[str, str]:
    _limpiar()
    pdfs = _pdf_dir(destino)
    return {
        "OUTCOMES_LOTE1": str(_outcomes_validos(pdfs, destino)),
        "PLAN_PDF": str(min((REPO / "tests/fixtures/facturas").glob("*.pdf"))),
        "FACTURAS_LOTE1": str(pdfs),
        "DESTINO": str(STAGE_TMP / f"delivery-{destino}"),
    }


def test_staging_sin_lote2_dos_entregables_y_commit():
    dest = STAGE_TMP / "delivery-basic"
    r = _run(_entorno("basic"))
    assert r.returncode == 0, r.stderr
    contenido = sorted(p.name for p in dest.iterdir() if p.name != ".git")
    assert contenido == ["albertitos_plan.pdf", "outcomes.jsonl"]
    # repo git local, sin remote
    log = subprocess.run(["git", "-C", str(dest), "log", "--oneline"],
                         check=False, capture_output=True, text=True)
    assert len(log.stdout.splitlines()) == 1
    remotes = subprocess.run(["git", "-C", str(dest), "remote"],
                             check=False, capture_output=True, text=True)
    assert remotes.stdout.strip() == ""
    assert "lote 2 pendiente" in r.stdout or "Falta outcomes_lote2" in r.stdout


def test_staging_idempotente_dos_ejecuciones_mismo_estado():
    env = _entorno("idem")
    r1 = _run(env)
    dest = Path(env["DESTINO"])
    log1 = subprocess.run(["git", "-C", str(env["DESTINO"]), "rev-list",
                           "HEAD", "--count"], check=False, capture_output=True, text=True)
    contenido1 = sorted(p.name for p in dest.iterdir())
    r2 = _run(env)
    log2 = subprocess.run(["git", "-C", str(env["DESTINO"]), "rev-list",
                           "HEAD", "--count"], check=False, capture_output=True, text=True)
    assert r1.returncode == r2.returncode == 0
    assert contenido1 == sorted(p.name for p in dest.iterdir())
    # idempotente: no acumula commits ni archivos
    assert log1.stdout.strip() == log2.stdout.strip() == "1"


def test_staging_con_lote2_tres_entregables():
    env = _entorno("full")
    pdfs2 = _pdf_dir("lote2")
    env["OUTCOMES_LOTE2"] = str(_outcomes_validos(pdfs2, "lote2"))
    env["FACTURAS_LOTE2"] = str(pdfs2)
    r = _run(env)
    assert r.returncode == 0, r.stderr
    dest = Path(env["DESTINO"])
    contenido = sorted(p.name for p in dest.iterdir() if p.name != ".git")
    assert contenido == ["albertitos_plan.pdf", "outcomes.jsonl",
                         "outcomes_lote2.jsonl"]


def test_staging_falla_limpio_con_jsonl_invalido():
    env = _entorno("invalido")
    out = Path(env["OUTCOMES_LOTE1"])
    out.write_text('{"file_id": "a.pdf", "result": "QUIZAS"}\n', encoding="utf-8")
    r = _run(env)
    assert r.returncode != 0
    assert "no pasa el validador" in (r.stderr + r.stdout)
    # nada se copió: el destino no existe
    assert not Path(env["DESTINO"]).exists()


def test_staging_falla_limpio_sin_lote1():
    env = _entorno("sinlote1")
    del env["OUTCOMES_LOTE1"]  # no existe en la raíz del repo
    r = _run(env)
    assert r.returncode != 0
    assert "outcomes.jsonl" in (r.stderr + r.stdout)


def test_staging_falla_con_secreto():
    env = _entorno("secreto")
    out = Path(env["OUTCOMES_LOTE1"])
    out.write_text('{"file_id": "a.pdf", "result": "PAGAR"}  # apiKey=hola\n',
                   encoding="utf-8")
    r = _run(env)
    assert r.returncode != 0
    assert "secreto" in (r.stderr + r.stdout)


def test_pdf_compilado_en_el_repo_de_entrega():
    """El PDF compilado de verdad está staged (NO commiteado en la solución)."""
    delivery = Path.home() / "delivery-repo"
    if not (delivery / "albertitos_plan.pdf").exists():
        import pytest

        pytest.skip("staging real aún no ejecutado en esta máquina")
    contenido = sorted(p.name for p in delivery.iterdir() if p.name != ".git")
    assert "albertitos_plan.pdf" in contenido
    from pypdf import PdfReader

    reader = PdfReader(delivery / "albertitos_plan.pdf")
    assert len(reader.pages) >= 2


def test_staging_ignora_artefactos_extra_de_la_raiz():
    """T27: el resumen de Alberto (y cualquier otro artefacto de la solución)
    NO entra en el repo de entrega — la raíz queda EXACTAMENTE con los
    entregables del contrato, aunque existan en la raíz de la solución."""
    resumen = REPO / "resumen_alberto.pdf"
    existed = resumen.exists()
    resumen.write_bytes(b"%PDF-fake-resumen")
    try:
        dest = STAGE_TMP / "delivery-resumen"
        env = _entorno("resumen")
        env["DESTINO"] = str(dest)
        r = _run(env)
        assert r.returncode == 0, r.stderr
        contenido = sorted(p.name for p in dest.iterdir() if p.name != ".git")
        assert contenido == ["albertitos_plan.pdf", "outcomes.jsonl"], (
            "el contrato manda EXACTAMENTE los entregables; el resumen no entra"
        )
    finally:
        if existed:
            resumen.unlink()
        else:
            resumen.unlink(missing_ok=True)
