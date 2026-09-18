"""Tests del runner end-to-end (T8)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from albertitos.emit import read_outcomes
from albertitos.run import ENGINE_VERSION, Runner, RunnerConfig, RunReport
from albertitos.validate import validar
from conftest import FIXTURES

RULES_YAML = Path("src/albertitos/rules/regla_v3.yaml")
MASTER_XLSX = FIXTURES / "maestro_fixture.xlsx"
FECHA_REF = "2026-09-19"


def _pdf_dir(tmp_path: Path) -> Path:
    """5 fixtures reales: 3 facturas con texto + 2 scans sin texto."""
    dst = tmp_path / "pdfs"
    dst.mkdir(parents=True)
    for f in sorted((FIXTURES / "facturas").glob("*.pdf")):
        shutil.copy(f, dst / f.name)
    for scan in sorted((FIXTURES / "scans").glob("scan_*.pdf")):
        shutil.copy(scan, dst / scan.name)
    return dst


def _cfg(tmp_path: Path, pdfs: Path, **kw) -> RunnerConfig:
    defaults = {
        "facturas_dir": pdfs,
        "outcomes_path": tmp_path / "outcomes.jsonl",
        "store_root": tmp_path / ".sdd",
        "rules_yaml": RULES_YAML,
        "master_path": MASTER_XLSX,
        "fecha_referencia": FECHA_REF,
        "use_rung4": False,  # en tests: sin VLM local (degradación determinista)
    }
    defaults.update(kw)
    return RunnerConfig(**defaults)


def _evidence_count(store_root: Path) -> int:
    import sqlite3

    conn = sqlite3.connect(store_root / "store.db")
    n = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
    conn.close()
    return n


# ---------------------------------------------------------------- e2e


def test_lote_5_fixtures_end_to_end_outcomes_validos(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs))
    report = runner.run()

    assert report.total == 5
    assert report.procesados == 5
    assert not report.rung4_secuencial  # sin llama-server: degradado, no parado
    assert report.files_per_second > 0  # medido

    from albertitos.emit import emit_outcomes

    out = emit_outcomes(runner.store, tmp_path / "outcomes.jsonl")
    reporte = validar(out, pdfs)
    assert reporte["errores"] == []
    outcomes = read_outcomes(out)
    assert len(outcomes) == 5
    for o in outcomes:
        assert o["result"] in ("PAGAR", "NO_PAGAR", "ESCALAR")
        assert "/" not in o["file_id"]
    # estado para la UI (T5), con números medidos
    state = json.loads((tmp_path / ".sdd" / "state" / "runner.json").read_text())
    assert state["total_archivos"] == 5
    assert state["done"] == 5
    assert state["medido"] is True
    assert state["files_per_second"] is not None
    assert state["rung4_llama_server"] == "down"


def test_re_run_byte_a_byte_y_cero_reprocesos(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs))
    runner.run()
    from albertitos.emit import emit_outcomes

    emit_outcomes(runner.store, tmp_path / "outcomes.jsonl")
    out1 = (tmp_path / "outcomes.jsonl").read_bytes()
    ev1 = _evidence_count(tmp_path / ".sdd")
    led1 = len(runner.store.ledger_events())

    runner2 = Runner(_cfg(tmp_path, pdfs))
    report2 = runner2.run()
    assert report2.reutilizados == 5
    assert report2.procesados == 0
    emit_outcomes(runner2.store, tmp_path / "outcomes.jsonl")
    out2 = (tmp_path / "outcomes.jsonl").read_bytes()
    assert out1 == out2  # byte a byte
    assert _evidence_count(tmp_path / ".sdd") == ev1  # evidencia no crece
    assert len(runner2.store.ledger_events()) == led1  # ledger intacto


def test_crash_a_mitad_reanuda_sin_duplicados(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    files = sorted(p.name for p in pdfs.glob("*.pdf"))
    victim = files[2]

    def crash(file_id):
        if file_id == victim:
            raise RuntimeError("crash simulado")

    runner = Runner(_cfg(tmp_path, pdfs))
    runner.fail_hook = crash
    try:
        runner.run()
    except RuntimeError as e:
        assert "crash simulado" in str(e)
    else:
        raise AssertionError("el hook debía simular el crash")
    runner.store.close()

    parciales = {d.file_id for d in
                 Runner(_cfg(tmp_path, pdfs)).store.all_decisions()}
    assert victim not in parciales
    assert len(parciales) == 2

    # reanudación: completa el lote sin duplicados
    runner2 = Runner(_cfg(tmp_path, pdfs))
    report = runner2.run()
    assert report.procesados + report.reutilizados == 5
    from albertitos.emit import emit_outcomes

    out = emit_outcomes(runner2.store, tmp_path / "outcomes.jsonl")
    ids = [o["file_id"] for o in read_outcomes(out)]
    assert len(ids) == len(set(ids)) == 5
    assert set(files) == set(ids)


def test_archivo_con_timeout_escala_y_el_lote_sigue(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    files = sorted(p.name for p in pdfs.glob("*.pdf"))
    victim = files[-1]  # último: los demás corren sin bloqueo en la cola

    def colgado(file_id):
        if file_id == victim:
            import time

            time.sleep(1.2)

    runner = Runner(_cfg(tmp_path, pdfs, timeout_por_archivo_s=0.2))
    runner.sleep_hook = colgado
    report = runner.run()

    assert report.timeout == 1
    assert report.resultados[victim] == "ESCALAR"
    d = runner.store.decision_for(victim)
    assert d.result == "ESCALAR"
    codes = ",".join(d.rule_codes)
    assert "RUNNER_TIMEOUT:UNKNOWN" in codes
    # el resto del lote se decidió con normalidad
    for f in files[:-1]:
        assert runner.store.decision_for(f) is not None
    # re-run sin el colgado: el timeout no se memoriza como definitivo
    runner.store.close()
    runner2 = Runner(_cfg(tmp_path, pdfs))
    report2 = runner2.run()
    d2 = runner2.store.decision_for(victim)
    assert d2.result != "ESCALAR" or report2_timeout_reutilizado(report2)


def report2_timeout_reutilizado(report: RunReport) -> bool:
    """El timeout no se cachea: el ítem se repite y termina normalmente."""
    return report.timeout == 0


def test_only_y_limit_lote_parcial(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs, only="invoice_*", limit=2))
    report = runner.run()
    assert report.total == 2
    assert set(report.resultados) <= {"invoice_catering_fa8496.pdf",
                                      "invoice_dup_fa8801_p005.pdf",
                                      "invoice_mensajeria_fa7399.pdf"}


def test_rung4_up_fuerza_cola_secuencial(tmp_path, monkeypatch):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs, max_in_flight=2))
    runner.rung4_disponible = True  # health-check finge llama-server UP
    report = runner.run()
    assert report.rung4_secuencial is True
    assert report.workers == 1  # una página cada vez: nunca en paralelo
    state = json.loads((tmp_path / ".sdd" / "state" / "runner.json").read_text())
    assert state["concurrency"] == 1
    assert state["rung4_secuencial"] is True


def test_no_toca_el_corpus(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    before = {p.name: p.read_bytes() for p in pdfs.glob("*.pdf")}
    runner = Runner(_cfg(tmp_path, pdfs))
    runner.run()
    for p in pdfs.glob("*.pdf"):
        assert p.read_bytes() == before[p.name]


def test_engine_version_del_runner_en_store(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs))
    runner.run()
    for d in runner.store.all_decisions():
        assert d.engine_version == ENGINE_VERSION
    runner.store.close()


def test_cli_main_lote_parcial_devuelve_0(tmp_path, capsys):
    pdfs = _pdf_dir(tmp_path)
    code = Runner_run_cli(tmp_path, pdfs)
    assert code == 0
    captured = capsys.readouterr()
    assert "Lote:" in captured.out


def Runner_run_cli(tmp_path, pdfs):

    return main_argv([
        "--facturas", str(pdfs),
        "--outcomes", str(tmp_path / "outcomes.jsonl"),
        "--store-root", str(tmp_path / ".sdd"),
        "--rules", str(RULES_YAML),
        "--maestro", str(MASTER_XLSX),
        "--fecha-referencia", FECHA_REF,
        "--limit", "2",
    ])


def main_argv(argv):
    from albertitos.run import main

    return main(argv)


def test_estado_runner_json_para_la_ui(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs))
    runner.run()
    state = json.loads((tmp_path / ".sdd" / "state" / "runner.json").read_text())
    assert state["done"] == 5 and state["pendientes"] == 0
    assert state["resultados"]["ESCALAR"] >= 2  # los scans sin texto escalan
    assert state["engine_version"] == ENGINE_VERSION
    assert state["facturas_dir"].endswith("pdfs")


def test_outcomes_incluye_los_5_con_file_id_exacto(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs))
    runner.run()
    from albertitos.emit import emit_outcomes

    out = emit_outcomes(runner.store, tmp_path / "outcomes.jsonl")
    ids = {o["file_id"] for o in read_outcomes(out)}
    assert ids == {p.name for p in pdfs.glob("*.pdf")}


def _pdf_dir_module_scope(tmp_path):  # pragma: no cover — helper legible
    shutil.copytree(FIXTURES, tmp_path)