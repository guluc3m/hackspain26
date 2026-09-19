"""T38-F6 · los overrides humanos de la UI SE CONSUMEN.

El bucle de revisión no puede ser un callejón sin salida: el override se
inyecta como candidato de extracción (extractor="humano", conf 1.0,
provenance), la decisión la recalcula el motor determinista, y el override
queda marcado como consumido (append-only) para no re-aplicarse.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from albertitos.extract.review import ReviewQueue
from albertitos.run import Runner, RunnerConfig, aplicar_overrides
from albertitos.types import ExtractionField
from conftest import FIXTURES

RULES_YAML = Path("src/albertitos/rules/regla_v3.yaml")
MASTER_XLSX = FIXTURES / "maestro_fixture.xlsx"
FECHA_REF = "2026-09-19"


# ------------------------------------------------- función pura (inyección)

def _campo(tipo: str, valor, extractor="regex", conf=0.9) -> ExtractionField:
    from albertitos.types import Candidate

    return ExtractionField(
        type=tipo, timestamp=0.0,
        values=[Candidate(extractor, valor, conf, f"{tipo}-ref")],
    )


def test_override_numerico_se_convierte_y_se_inyecta():
    total = _campo("total", 1409.40)
    ov = {"file_id": "f.pdf", "campo": "total", "valor": "1.705,37",
          "cuando": "2026-09-19 08:00:00"}
    fields, aplicados, descartados = aplicar_overrides([total], [ov])
    assert aplicados and not descartados
    vals = {f.type: f.values for f in fields}["total"]
    humano = [c for c in vals if c.extractor == "humano"]
    assert len(humano) == 1
    assert humano[0].value == 1705.37  # float: el motor lo compara como número
    assert humano[0].confidence == 1.0
    assert humano[0].feature_ref == "override:2026-09-19 08:00:00"


def test_override_campo_inexistente_crea_el_campo():
    nif = _campo("nif", "J99999999")
    ov = {"file_id": "f.pdf", "campo": "pedido", "valor": "PO-2026-0222",
          "cuando": "cuando-1"}
    fields, aplicados, descartados = aplicar_overrides([nif], [ov])
    assert aplicados and not descartados
    pedidos = [f for f in fields if f.type == "pedido"]
    assert len(pedidos) == 1
    assert pedidos[0].values[0].extractor == "humano"


def test_override_no_convertible_queda_descartado_con_señal():
    total = _campo("total", 1409.40)
    ov = {"file_id": "f.pdf", "campo": "total", "valor": "n/d",
          "cuando": "cuando-2"}
    fields, aplicados, descartados = aplicar_overrides([total], [ov])
    assert not aplicados and descartados == [ov]
    assert all(c.extractor != "humano" for c in fields[0].values)


def test_override_cadena_pierde_contra_humano_por_confianza():
    """El candidato humano (conf 1.0) es el de mayor confianza: _pick y
    _mejor_valor lo eligen — el humano propone el valor, el motor decide."""
    from albertitos.types import Candidate

    nif = ExtractionField(
        type="nif", timestamp=0.0,
        values=[Candidate("regex", "J99999999", 0.9, "ref")],
    )
    ov = {"file_id": "f.pdf", "campo": "nif", "valor": "B46102331",
          "cuando": "cuando-3"}
    fields, _, _ = aplicar_overrides([nif], [ov])
    best = max(fields[0].values, key=lambda c: c.confidence)
    assert best.extractor == "humano" and best.value == "B46102331"


# ------------------------------------------------- cola: pendiente/consumido

def _rq(tmp_path) -> ReviewQueue:
    rq = ReviewQueue(tmp_path / "review-queue")
    rq.root.mkdir(parents=True, exist_ok=True)
    return rq


def _override(campo="nif", valor="B46102331", cuando="t1") -> dict:
    return {"invoice_id": "inv-1", "file_id": "f.pdf", "campo": campo,
            "valor": valor, "nota": "", "cuando": cuando}


def test_ciclo_pendiente_marcar_consumido(tmp_path):
    rq = _rq(tmp_path)
    ov1 = _override(cuando="t1")
    ov2 = _override(campo="total", valor="100", cuando="t2")
    with rq.overrides_path.open("a", encoding="utf-8") as fh:
        for ov in (ov1, ov2):
            fh.write(json.dumps(ov, ensure_ascii=False) + "\n")

    pend = rq.read_overrides_pendientes()
    assert len(pend) == 2

    rq.marcar_consumidas([ov1])
    pend = rq.read_overrides_pendientes()
    assert len(pend) == 1 and pend[0]["cuando"] == "t2"

    # append-only: el histórico conserva TODAS las líneas, nada se reescribe
    lineas = rq.overrides_path.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 3  # ov1, ov2, marcador consumido
    assert json.loads(lineas[-1])["kind"] == "consumido"


def test_marcar_consumidas_vacio_es_no_op(tmp_path):
    rq = _rq(tmp_path)
    assert rq.marcar_consumidas([]) == 0
    assert not rq.overrides_path.exists()


# ------------------------------------------------- e2e con el runner real

def _pdfs(tmp_path: Path) -> Path:
    dst = tmp_path / "pdfs"
    dst.mkdir(parents=True)
    for f in sorted((FIXTURES / "facturas").glob("*.pdf")):
        shutil.copy(f, dst / f.name)
    return dst


def _cfg(tmp_path: Path, pdfs: Path, **kw) -> RunnerConfig:
    defaults = {
        "facturas_dir": pdfs,
        "outcomes_path": tmp_path / "outcomes.jsonl",
        "store_root": tmp_path / ".sdd",
        "rules_yaml": RULES_YAML,
        "master_path": MASTER_XLSX,
        "fecha_referencia": FECHA_REF,
        "use_rung4": False,
    }
    defaults.update(kw)
    return RunnerConfig(**defaults)


def test_e2e_override_se_consume_y_deja_evidencia(tmp_path):
    pdfs = _pdfs(tmp_path)
    runner = Runner(_cfg(tmp_path, pdfs))
    report = runner.run()
    file_id = min(report.resultados)

    # override humano vía la cola de revisión (mismo schema que la UI)
    rq = _rq(tmp_path / ".sdd")
    ov = {"invoice_id": "inv-x", "file_id": file_id, "campo": "total",
          "valor": "1.234,56", "nota": "prueba", "cuando": "t-e2e"}
    with rq.overrides_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(ov, ensure_ascii=False) + "\n")
    assert len(rq.read_overrides_pendientes()) == 1

    # re-proceso con --force: el override se inyecta y la decisión re-computada
    runner2 = Runner(_cfg(tmp_path, pdfs, force=True, only=file_id))
    runner2.run()

    # evidencia stage=override outcome=aplicado (provenance completo)
    rows = runner2.store.count_evidence(file_id=file_id)
    assert rows > 0
    import sqlite3

    conn = sqlite3.connect(tmp_path / ".sdd" / "store.db")
    n = conn.execute(
        "SELECT COUNT(*) FROM evidence WHERE file_id=? AND stage='override'"
        " AND outcome='aplicado'", (file_id,)
    ).fetchone()[0]
    conn.close()
    assert n == 1

    # el override queda CONSUMIDO: un re-run posterior no lo re-aplica
    pend = rq.read_overrides_pendientes()
    assert pend == []
    marcadores = [
        json.loads(ln)
        for ln in rq.overrides_path.read_text(encoding="utf-8").splitlines()
    ]
    assert any(m.get("kind") == "consumido" for m in marcadores)

    # idempotencia: forzar OTRA vez sin overrides pendientes no añade evidencia
    runner3 = Runner(_cfg(tmp_path, pdfs, force=True, only=file_id))
    runner3.run()
    conn = sqlite3.connect(tmp_path / ".sdd" / "store.db")
    n2 = conn.execute(
        "SELECT COUNT(*) FROM evidence WHERE file_id=? AND stage='override'"
        " AND outcome='aplicado'", (file_id,)
    ).fetchone()[0]
    conn.close()
    assert n2 == 1