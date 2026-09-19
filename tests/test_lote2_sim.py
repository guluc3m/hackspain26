"""Tests de T21: readiness del lote 2 — simulación de extremo a extremo.

Sin red (use_rung4=False ⇒ rungs 4/5 degradados deterministas) y determinista.
El store real (`.sdd/store.db`) y `outcomes.jsonl` del lote 1 NO se tocan.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from albertitos.emit import emit_outcomes
from albertitos.lote2 import (
    RUN_LOTE2_BASE,
    RUN_LOTE2_DATO,
    RUN_LOTE2_V4,
    Lote2SimConfig,
    render,
    simular_lote2,
)
from albertitos.store import Store
from albertitos.validate import validar

REPO = Path(__file__).resolve().parent.parent
SIM_ROOT = REPO / ".sdd" / "pytest-tmp" / "lote2"


def _limpiar() -> None:
    if SIM_ROOT.exists():
        shutil.rmtree(SIM_ROOT)
    SIM_ROOT.mkdir(parents=True)


def _cfg(**kwargs) -> Lote2SimConfig:
    """Config de simulación apuntando al sandbox (sin borrar: solo tests que
    quieran arrancar de cero llaman a _limpiar() antes)."""
    SIM_ROOT.mkdir(parents=True, exist_ok=True)
    return Lote2SimConfig(store_root=SIM_ROOT, fecha_referencia="2026-09-19",
                          **kwargs)


def test_simulacion_completa_determinista_sin_red():
    """Dos corridas ⇒ mismo JSON byte a byte (sin timestamps ni timings)."""
    _limpiar()
    r1 = simular_lote2(_cfg())
    m1 = SIM_ROOT / "m1.json"
    m1.write_text(json.dumps(r1, ensure_ascii=False, sort_keys=True))
    r2 = simular_lote2(_cfg())
    m2 = SIM_ROOT / "m2.json"
    m2.write_text(json.dumps(r2, ensure_ascii=False, sort_keys=True))
    assert m1.read_bytes() == m2.read_bytes()
    # el CLI escribe el mismo JSON que la llamada directa
    uv = shutil.which("uv")
    subprocess.run(
        [uv, "run", "python", "-m", "albertitos.lote2", "--dry-run",
         "--store-root", str(SIM_ROOT),
         "--metrics", str(SIM_ROOT / "metrics" / "lote2-sim.json")],
        cwd=REPO, check=True, capture_output=True,
    )
    m3 = SIM_ROOT / "metrics" / "lote2-sim.json"
    assert json.loads(m3.read_text()) == r1


def test_ingesta_lote_externo_ingesta_separada():
    r = simular_lote2(_cfg())
    i = r["ingesta"]
    assert i["facturas"] == 10
    assert i["store_sandbox"].endswith("lote2-sim/store")
    assert i["run_id"] == RUN_LOTE2_BASE
    assert i["ledger_separado"] is True
    assert i["resultados"] == {"PAGAR": 10, "NO_PAGAR": 0, "ESCALAR": 0}
    # file_id = basename exacto (fixtures con nombres reales del corpus)
    assert "2026-01-08_P001.pdf" in i["file_id_exacto"]
    assert not any("/" in f for f in i["file_id_exacto"])


def test_v4_como_datos_activada_cambia_el_subconjunto_esperado():
    r = simular_lote2(_cfg())
    v4 = r["v4_activada"]
    # importe_minimo 3000: 5 facturas del lote10 quedan debajo (medido)
    assert v4["cambiados"] == 5
    assert v4["sin_cambio"] == 5
    assert v4["resumen"]["cambiados"] == 5


def test_cambio_de_dato_solo_afecta_los_que_cruzan_y_el_historico_coexiste():
    r = simular_lote2(_cfg())
    d = r["cambio_dato"]
    # parche: NIF del proveedor P001 ⇒ exactamente UNA factura afectada
    assert d["cambiados"] == 1
    assert d["resumen"]["afectados"] == 1
    assert r["historico"]["coexiste"] is True
    assert set(r["historico"]["runs"]) == {
        RUN_LOTE2_BASE, RUN_LOTE2_V4, RUN_LOTE2_DATO,
    }
    store = Store(SIM_ROOT / "lote2-sim" / "store")
    try:
        base = {x.file_id: x.result for x in store.run_decisions(RUN_LOTE2_BASE)}
        v4 = {x.file_id: x.result for x in store.run_decisions(RUN_LOTE2_V4)}
        dato = {x.file_id: x.result for x in store.run_decisions(RUN_LOTE2_DATO)}
        # el histórico de base y v4 sigue intacto (jamás se sobreescribe)
        assert len(base) == 10 and len(v4) == 10
        # el run de dato re-decide SOLO el afectado y coexiste
        assert set(dato) == {"2026-01-08_P001.pdf"}
        # 2026-01-08_P001 (total 3012.89 > mínimo): PAGAR → NO_PAGAR con el NIF fuera
        assert v4["2026-01-08_P001.pdf"] == "PAGAR"
        assert dato["2026-01-08_P001.pdf"] == "NO_PAGAR"
    finally:
        store.close()


def test_emision_lote2_validada_y_lote1_intacto():
    store_db = REPO / ".sdd" / "store.db"
    store_antes = (hashlib.sha256(store_db.read_bytes()).hexdigest()
                   if store_db.exists() else None)

    r = simular_lote2(_cfg())
    assert r["emision"]["validacion"] == "OK"
    assert r["emision"]["lineas"] == 10
    assert r["emision"]["errores"] == []
    # el lote 1 no se tocó: byte a byte
    if store_db.exists():
        assert hashlib.sha256(store_db.read_bytes()).hexdigest() == store_antes
    assert r["lote1_inalterado"] is True


def test_emit_scope_lote_en_store_mixto():
    """Producción (sábado): lote 1 y lote 2 en el MISMO store ⇒ la emisión del
    lote 2 con only_files produce SOLO sus líneas y no mezcla el lote 1."""
    store = Store(SIM_ROOT / "mixto")
    try:
        r = simular_lote2(_cfg())
        # mezclar: las 10 decisiones del lote 2 (3 runs del sandbox) + 3
        # file_id "del lote 1" en el MISMO store (lo que pasará el sábado)
        from albertitos.types import Decision, RuleVerdict

        sandbox = Store(SIM_ROOT / "lote2-sim" / "store")
        try:
            for run in (RUN_LOTE2_BASE, RUN_LOTE2_V4, RUN_LOTE2_DATO):
                for d in sandbox.run_decisions(run):
                    decision = Decision(
                        invoice_id=d.invoice_id, file_id=d.file_id,
                        result=d.result,
                        rule_verdicts=[RuleVerdict(c.split(":")[0], "PASS", "", {})
                                       for c in d.rule_codes],
                        config_snapshot={"config_version": d.config_version},
                    )
                    store.record_decision(decision, d.sha256,
                                          numero_factura=d.numero_factura,
                                          pedido=d.pedido, engine_version="t",
                                          run_id=run, nif=d.nif, iban=d.iban)
        finally:
            sandbox.close()
        for i, fid in enumerate(("lote1_a.pdf", "lote1_b.pdf", "lote1_c.pdf")):
            decision = Decision(
                invoice_id=f"inv-lote1-{i}", file_id=fid, result="PAGAR",
                rule_verdicts=[RuleVerdict("X", "PASS", "", {})],
                config_snapshot={"config_version": "v3.0-test"},
            )
            store.record_decision(decision, f"sha-lote1-{i}",
                                  numero_factura=f"L1-{i}", pedido=f"PO-L1-{i}",
                                  engine_version="t", run_id="base",
                                  nif=f"B1000000{i}", iban="")
        # emisión del lote 2: SOLO los 10 file_id del lote simulado
        out = SIM_ROOT / "outcomes_lote2_mixed.jsonl"
        lote2_ids = set(r["ingesta"]["file_id_exacto"])
        emit_outcomes(store, out, only_files=lote2_ids)
        lineas = out.read_text().strip().splitlines()
        assert len(lineas) == 10
        ids = {json.loads(ln)["file_id"] for ln in lineas}
        assert ids == lote2_ids
        # sin scope: incluye también las 3 mezcladas del lote 1
        out_all = SIM_ROOT / "outcomes_all_mixed.jsonl"
        emit_outcomes(store, out_all)
        assert len(out_all.read_text().strip().splitlines()) == 13
    finally:
        store.close()


def test_validador_de_contrato_sobre_el_outcomes_del_sim():
    """El validador oficial pasa contra el directorio del lote simulado."""
    simular_lote2(_cfg())
    v = validar(SIM_ROOT / "lote2-sim" / "outcomes_lote2.jsonl",
                Path("tests/fixtures/lote10"))
    assert v.get("errores") == []


def test_render_legible():
    r = simular_lote2(_cfg())
    texto = render(r)
    assert "SIMULACIÓN DEL LOTE 2" in texto
    assert "regla v4 como datos" in texto
    assert "outcomes.jsonl del lote 1 intacto" in texto