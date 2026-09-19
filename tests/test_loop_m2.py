"""T33-M2: estado del lote en una query — mismo JSON, O(N) por tick."""

import json
from pathlib import Path

from albertitos.run import Runner, RunnerConfig
from albertitos.store import Store
from conftest import FIXTURES, fixture_path

RULES = Path("src/albertitos/rules/regla_v3.yaml")
MAESTRO = fixture_path("maestro_fixture.xlsx")


def _store(tmp_path: Path) -> Store:
    return Store(tmp_path / "sdd")


def test_resultados_por_file_mapa_correcto(tmp_path):
    store = _store(tmp_path)
    from albertitos.types import Decision

    for i in (1, 2, 3):
        d = Decision(invoice_id=f"inv-{i}", file_id=f"f{i}.pdf",
                     result="PAGAR" if i % 2 else "ESCALAR",
                     rule_verdicts=[], config_snapshot={"config_version": "t"})
        store.record_decision(d, f"sha-{i}", numero_factura=f"N{i}",
                              pedido=f"PO-{i}", engine_version="t")
    s = store.resultados_por_file(["f1.pdf", "f2.pdf", "f3.pdf", "no-existe.pdf"])
    assert s == {"f1.pdf": "PAGAR", "f2.pdf": "ESCALAR", "f3.pdf": "PAGAR"}
    assert store.resultados_por_file([]) == {}
    store.close()


def test_estado_json_byte_identico_tras_el_cambio(tmp_path):
    """El state/runner.json que consume la UI no cambia de formato."""

    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    for f in sorted((FIXTURES / "facturas").glob("*.pdf"))[:3]:
        f2 = pdfs / f.name
        f2.write_bytes(f.read_bytes())
    store = _store(tmp_path)

    r = Runner(RunnerConfig(
        facturas_dir=pdfs, outcomes_path=tmp_path / "outcomes.jsonl",
        store_root=tmp_path / "sdd", rules_yaml=RULES, master_path=fixture_path("maestro_fixture.xlsx"),
        fecha_referencia="2026-09-19", use_rung4=False,
    ))
    r.run()
    state = json.loads((tmp_path / "sdd" / "state" / "runner.json").read_text())
    # formato estable para la UI T5: mismas claves y conteos
    assert set(state) >= {"total_archivos", "done", "pendientes",
                          "resultados", "medido"}
    assert state["medido"] is True
    assert state["done"] == 3
    assert state["resultados"] == {
        "PAGAR": state["resultados"]["PAGAR"],
        "NO_PAGAR": state["resultados"]["NO_PAGAR"],
        "ESCALAR": state["resultados"]["ESCALAR"],
    }
    store.close()
