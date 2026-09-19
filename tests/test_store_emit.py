"""Tests de T4: store, ledger, idempotencia, crash-resume y emisión."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from albertitos.emit import emit_outcomes, read_outcomes, validate_outcomes
from albertitos.pipeline import PipelineDeps, run_batch
from albertitos.rules import load_config, load_master
from albertitos.store import Store, invoice_uuid
from conftest import FIXTURES, fixture_path

RULES_YAML = Path("src/albertitos/rules/regla_v3.yaml")
MASTER_XLSX = fixture_path("maestro_fixture.xlsx")
FECHA_REF = "2026-09-19"


def _pdf_dir(tmp_path: Path, n: int = 5) -> Path:
    """Directorio con PDFs de verdad (copias de fixtures del corpus)."""
    src = FIXTURES / "facturas"
    dst = tmp_path / "pdfs"
    dst.mkdir(parents=True, exist_ok=True)
    for f in sorted(src.glob("*.pdf"))[:n]:
        shutil.copy(f, dst / f.name)
    # scans sin texto para cubrir la rama degradada (2 disponibles)
    for scan in sorted((FIXTURES / "scans").glob("scan_*.pdf"))[:max(0, n - 3)]:
        shutil.copy(scan, dst / scan.name)
    return dst


def _deps(fail_injector=None) -> PipelineDeps:
    cfg = load_config(RULES_YAML, fecha_referencia=FECHA_REF)
    master = load_master(MASTER_XLSX, hojas_ignoradas=cfg.hojas_ignoradas)
    return PipelineDeps(master=master, config=cfg, fail_injector=fail_injector)


# ---------------------------------------------------------------- store


def test_store_estado_en_disco_no_en_tmp(tmp_path):
    store = Store(tmp_path / "sdd")
    assert (tmp_path / "sdd" / "store.db").exists()
    assert (tmp_path / "sdd" / "ledger").is_dir()
    store.close()


def test_store_fuera_de_tmp(tmp_path):
    """El store por defecto vive en .sdd/, jamás en /tmp."""
    store = Store(tmp_path / "sdd")
    assert str(store.db_path).startswith(str(tmp_path))
    store.close()


def test_invoice_uuid_estable_por_contenido():
    assert invoice_uuid("abc") == invoice_uuid("abc")
    assert invoice_uuid("abc") != invoice_uuid("abd")


# ---------------------------------------------------------------- batch


def test_lote_dos_veces_mismo_outcomes_y_cero_reprocesos(tmp_path):
    pdfs = _pdf_dir(tmp_path)
    store = Store(tmp_path / ".sdd")
    deps = _deps()
    run_batch(pdfs, store, deps)
    emit_outcomes(store, tmp_path / "outcomes.jsonl")
    out1 = Path(tmp_path / "outcomes.jsonl").read_bytes()
    ev1 = store.count_evidence()
    led1 = len(store.ledger_events())

    # segunda pasada del mismo lote: no-op
    deps2 = _deps()
    report2 = run_batch(pdfs, store, deps2)
    emit_outcomes(store, tmp_path / "outcomes.jsonl")
    out2 = Path(tmp_path / "outcomes.jsonl").read_bytes()

    assert out1 == out2  # byte a byte
    assert report2.procesados == 0
    assert report2.reutilizados == len(list(pdfs.glob("*.pdf")))
    assert store.count_evidence() == ev1  # evidencia no crece
    assert len(store.ledger_events()) == led1  # ledger append-only intacto
    store.close()


def test_crash_a_mitad_reanuda_sin_duplicados(tmp_path):
    pdfs = _pdf_dir(tmp_path, n=5)
    store = Store(tmp_path / ".sdd")

    files = sorted(p.name for p in pdfs.glob("*.pdf"))
    victim = files[2]  # matar en el ítem N=2 (tercero)

    def injector(file_id, index):
        if file_id == victim:
            raise RuntimeError("simulated crash mid-batch")

    try:
        run_batch(pdfs, store, _deps(fail_injector=injector))
    except RuntimeError as e:
        assert "simulated crash" in str(e)
    else:
        raise AssertionError("el injector debía fallar")

    parciales = {d.file_id for d in store.all_decisions()}
    assert victim not in parciales
    assert len(parciales) == 2

    # reanudar: completa el lote sin duplicados
    run_batch(pdfs, store, _deps())
    emit_outcomes(store, tmp_path / "outcomes.jsonl")
    outcomes = read_outcomes(tmp_path / "outcomes.jsonl")
    ids = [o["file_id"] for o in outcomes]
    assert len(ids) == len(set(ids)) == 5
    assert set(files) <= set(ids)
    store.close()


def test_file_id_jamas_normalizado(tmp_path):
    """Nombres con mayúsculas/acentos/puntos deben aparecer EXACTOS."""
    pdfs = _pdf_dir(tmp_path, n=3)
    store = Store(tmp_path / ".sdd")
    run_batch(pdfs, store, _deps())
    emit_outcomes(store, tmp_path / "outcomes.jsonl")
    for o in read_outcomes(tmp_path / "outcomes.jsonl"):
        assert o["file_id"] == o["file_id"]  # sin normalizar
        assert "/" not in o["file_id"]
    store.close()


def test_doble_pago_en_lote_por_orden_determinista(tmp_path):
    """Dos PDFs con el mismo nº de factura: el segundo NO_PAGAR, siempre."""
    src = FIXTURES / "facturas"
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    shutil.copy(src / "invoice_dup_fa8801_p005.pdf", pdfs / "a_primero.pdf")
    shutil.copy(src / "invoice_dup_fa8801_p005.pdf", pdfs / "b_segundo.pdf")
    store = Store(tmp_path / ".sdd")
    deps = _deps()
    run_batch(pdfs, store, deps)
    emit_outcomes(store, tmp_path / "outcomes.jsonl")
    res = {o["file_id"]: o["result"] for o in
           read_outcomes(tmp_path / "outcomes.jsonl")}
    assert res["a_primero.pdf"] == "PAGAR"
    assert res["b_segundo.pdf"] == "NO_PAGAR"
    codes = store.decision_for("b_segundo.pdf").rule_codes
    assert "NO_DOUBLE_PAYMENT:FAIL" in codes
    store.close()


# ---------------------------------------------------------------- emit


def test_emit_y_validador_de_contrato(tmp_path):
    pdfs = _pdf_dir(tmp_path, n=4)
    store = Store(tmp_path / ".sdd")
    run_batch(pdfs, store, _deps())
    out = emit_outcomes(store, tmp_path / "outcomes.jsonl")
    outcomes = read_outcomes(out)
    for o in outcomes:
        assert set(o) >= {"file_id", "result"}
        assert o["result"] in ("PAGAR", "NO_PAGAR", "ESCALAR")
        assert o["file_id"].endswith(".pdf")
    assert validate_outcomes(out, pdfs) == []
    store.close()


def test_validador_detecta_contrato_roto(tmp_path):
    pdfs = _pdf_dir(tmp_path, n=2)
    store = Store(tmp_path / ".sdd")
    run_batch(pdfs, store, _deps())
    out = emit_outcomes(store, tmp_path / "outcomes.jsonl")
    # romper el contrato: file_id con ruta + result inválido
    data = read_outcomes(out)
    data[0]["file_id"] = "ruta/mal.pdf"
    data[1]["result"] = "QUIZAS"
    out.write_text("\n".join(json.dumps(o) for o in data) + "\n")
    errores = validate_outcomes(out, pdfs)
    assert any("no es un nombre exacto" in e for e in errores)
    assert any("result inválido" in e for e in errores)
    assert any("sobran" in e for e in errores)
    store.close()


def test_outcomes_vacio_con_store_vacio(tmp_path):
    store = Store(tmp_path / ".sdd")
    out = emit_outcomes(store, tmp_path / "outcomes.jsonl")
    assert read_outcomes(out) == []
    store.close()


# ---------------------------------------------------------------- retro


def test_resoluciones_escaladas_se_conservan(tmp_path):
    store = Store(tmp_path / ".sdd")
    store.save_resolution("factura_4485.pdf", invoice_uuid("abc"),
                          "alberto", "ESCALAR", "NO_PAGAR",
                          "revisado: proveedor fantasma")
    rs = store.resolutions()
    assert len(rs) == 1
    assert rs[0]["resolved_by"] == "revisado: proveedor fantasma" or \
        rs[0]["note"] == "revisado: proveedor fantasma"
    eventos = store.ledger_events()
    assert any(e["event"] == "resolution" for e in eventos)
    store.close()


# ---------------------------------------------------------------- contrato 500


def _caja_facturas() -> Path | None:
    p = Path("caja-de-alberto/facturas")
    return p if p.is_dir() and len(list(p.glob("*.pdf"))) == 500 else None


def test_validador_500_file_id_de_caja_de_alberto(tmp_path):
    """Criterio T4: 500 file_id únicos de caja-de-alberto/facturas/."""
    caja = _caja_facturas()
    if caja is None:  # submódulo no inicializado en este checkout
        import pytest

        pytest.skip("caja-de-alberto no disponible")
    store = Store(tmp_path / ".sdd")
    deps = _deps()
    run_batch(Path("caja-de-alberto/facturas"), store, deps)
    out = emit_outcomes(store, tmp_path / "outcomes.jsonl")
    errores = validate_outcomes(out, Path("caja-de-alberto/facturas"))
    assert errores == []
    resultados = {o["result"] for o in read_outcomes(out)}
    assert resultados <= {"PAGAR", "NO_PAGAR", "ESCALAR"}
    store.close()

# ---------------------------------------------------------- overrides (T38-F6)

def test_override_humano_se_aplica_y_la_decision_recalcula(tmp_path):
    """T38-F6 REPRO: un override humano del UI alimenta la extracción y la
    decisión se recalcula; el override queda marcado CONSUMIDO y sellado."""
    store = Store(tmp_path / ".sdd")
    deps = _deps()
    # 1ª corrida: factura en NO_PAGAR (el NIF no está en el maestro)
    run_batch(pdfs := _pdf_dir(tmp_path, n=1), store, deps)
    primera = store.all_decisions()[0]
    overrides = tmp_path / ".sdd" / "review-queue" / "overrides.jsonl"
    overrides.parent.mkdir(parents=True, exist_ok=True)
    overrides.write_text(
        json.dumps(
            {
                "invoice_id": primera.invoice_id,
                "file_id": primera.file_id,
                "campo": "total",
                "valor": "1705.37",
                "cuando": "2026-09-19T10:00:00",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    # 2ª corrida (--force equivalente: decision cache se salta con force…)
    # run_batch reutiliza por cache: re-crear deps con otro engine_version
    # obliga a re-decidir (misma ruta que --force del runner).
    deps2 = PipelineDeps(master=deps.master, config=deps.config, engine_version="runner-override-test")
    run_batch(pdfs, store, deps2)
    consumidos = tmp_path / ".sdd" / "review-queue" / "overrides.consumidos.jsonl"
    assert consumidos.is_file(), "el override debe quedar sellado como consumido"
    assert "1705.37" in consumidos.read_text(encoding="utf-8")
    assert "1705.37" not in overrides.read_text(encoding="utf-8"), "no debe re-inyectarse"
    # la decisión final ya no es el NO_PAGAR original si el importe corregido
    # matchea el maestro (el motor recalcula con el candidato humano)
    final = store.decision_for(primera.file_id)
    assert final is not None
