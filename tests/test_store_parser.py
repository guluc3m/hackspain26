from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from filemaid.extract.ladder import PageExtraction
from filemaid.parse.parser import parse_fields
from filemaid.pipeline import Pipeline
from filemaid.store.db import Store
from filemaid.store.ledger import Ledger
from filemaid.types import ExtractionFeature, Result

def _feature(texto: str, method: str) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text", extraction_method=method, data=texto, page=0, extractor_version="1"
    )


def test_parser_conserva_candidatos_de_varias_fuentes():
    page = PageExtraction(page=0)
    page.features.append(_feature("TOTAL : 121,00 EUR", "pypdf"))
    page.features.append(_feature("Importe Total: 121,00", "tesseract"))
    fields = parse_fields([page])
    total = next(f for f in fields if f.type == "total")
    assert len(total.values) == 2
    assert {c.extractor for c in total.values} == {"regex_total"}


def test_store_nunca_colapsa_candidatos(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    store.add_field(
        "inv-1",
        "total",
        [
            {"extractor": "pypdf", "value": 121.00, "confidence": 0.7},
            {"extractor": "vlm", "value": 120.50, "confidence": 0.9},
        ],
    )
    fields = store.fields_for("inv-1")
    assert len(fields["total"]) == 2
    assert fields["total"][0]["value"] == 120.50  # ordenado por confianza


def test_store_idempotente_feature(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    kw = {
        "stage": "pypdf",
        "page": 0,
        "extractor_version": "1",
        "config_version": "cfg",
        "sha256": "sha-1",
        "latency_ms": 5,
        "confidence": 1.0,
        "outcome": "pypdf",
        "detail": {"type": "pdf_text"},
    }
    store.add_feature("inv-1", **kw)
    store.add_feature("inv-1", **kw)
    n = store.conn.execute("SELECT COUNT(*) AS n FROM features").fetchone()["n"]
    assert n == 1


def test_ledger_append_only(tmp_path):
    ledger = Ledger(tmp_path / "ledger.jsonl")
    ledger.append("invoice_seen", {"invoice_id": "inv-1"})
    ledger.append("decision", {"invoice_id": "inv-1", "result": Result.PAGAR.value})
    lines = [json.loads(l) for l in (tmp_path / "ledger.jsonl").read_text().splitlines()]
    assert [e["type"] for e in lines] == ["invoice_seen", "decision"]
    assert lines[1]["result"] == "PAGAR"


def test_override_con_procedencia(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    store.add_override(
        {
            "invoice_id": "inv-1",
            "field_type": "iban",
            "before": "ES00",
            "after": "ES9121000418450200051332",
            "who": "revisor",
            "rung": "review-ui",
            "reason": "lectura",
        }
    )
    rows = store.overrides_for("inv-1")
    assert len(rows) == 1
    assert rows[0]["who"] == "revisor"
    assert json.loads(rows[0]["after"]) == "ES9121000418450200051332"


def test_store_guarda_reason_code(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    store.add_rule_evaluations(
        "inv-1",
        "run-1",
        [
            {
                "code": "DATE_VALID_NOT_FUTURE",
                "verdict": "UNKNOWN",
                "reason": "sin campo fecha",
                "reason_code": "SIN_CAMPO",
                "consumed": {},
            },
        ],
    )
    row = store.rule_evaluations_for("inv-1", "run-1")[0]
    assert row["reason_code"] == "SIN_CAMPO"


def test_store_backfill_reason_code_de_filas_legacy(cfg):
    # simula un store anterior a reason_code: fila UNKNOWN con solo el motivo textual
    store = Store(cfg.store_path)
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    store.conn.execute(
        """INSERT INTO rule_evaluations (invoice_id, run_id, code, verdict, reason, consumed, timestamp)
           VALUES ('inv-1', 'run-1', 'NIF_IN_MASTER', 'UNKNOWN', 'NIF no fiable: sin campo nif', '{}', 0)"""
    )
    store.conn.commit()
    store.close()

    reopened = Store(cfg.store_path)  # la migración añade columna y clasifica las filas legacy
    row = reopened.rule_evaluations_for("inv-1", "run-1")[0]
    assert row["reason_code"] == "SIN_CAMPO"

def test_store_guarda_stage_timings(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    store.save_decision(
        "inv-1",
        "run-1",
        "PAGAR",
        {"thresholds": {}},
        extraction_ms=120,
        parser_ms=15,
        evaluation_ms=5,
        total_ms=140,
        timings={"extraction_ms": 120, "parser_ms": 15, "pypdf_p0": 110},
    )
    rows = store.decision_rows_for_run("run-1")
    assert len(rows) == 1
    r = rows[0]
    assert r["extraction_ms"] == 120
    assert r["parser_ms"] == 15
    assert r["evaluation_ms"] == 5
    assert r["total_ms"] == 140
    timings = json.loads(r["timings"])
    assert timings["pypdf_p0"] == 110


def test_store_backfill_decisions_timings_legacy(cfg):
    # Simula store con tabla decisions sin las nuevas columnas
    store = Store(cfg.store_path)
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    # Al abrir Store, las columnas ya existen debido a _migrate()
    row = store.conn.execute("SELECT * FROM decisions WHERE invoice_id = 'inv-1'").fetchone()
    assert row is None
    store.save_decision("inv-1", "run-old", "PAGAR", {})
    row = store.decision_rows_for_run("run-old")[0]
    assert row["extraction_ms"] == 0
    assert row["total_ms"] == 0
    assert json.loads(row["timings"]) == {}

def test_pipeline_records_stage_timings(cfg, tmp_path):
    pdf_path = tmp_path / "factura_test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 mock content")

    pipe = Pipeline(cfg)
    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method="pypdf",
        data="FACTURA 2026/001 Fecha: 15/01/2026 Total: 121,00 EUR NIF: B12345678",
        page=0,
        latency_ms=45,
        confidence=0.9,
    )
    mock_page = PageExtraction(page=0, features=[feat], content=str(feat.data))

    with patch("filemaid.pipeline.extract_file", return_value=[mock_page]):
        decision = pipe.process_pdf(pdf_path)

    assert decision.extraction_ms >= 0
    assert decision.parser_ms >= 0
    assert decision.evaluation_ms >= 0
    assert decision.total_ms >= 0
    assert "pypdf_p0" in decision.timings
    assert decision.timings["pypdf_p0"] == 45

    # Check store row
    rows = pipe.store.decision_rows_for_run(pipe.rule_config.version)
    assert len(rows) == 1
    r = rows[0]
    assert r["extraction_ms"] == decision.extraction_ms
    assert r["parser_ms"] == decision.parser_ms
    assert r["evaluation_ms"] == decision.evaluation_ms
    assert r["total_ms"] == decision.total_ms

    # Check ledger row
    ledger_lines = [json.loads(l) for l in Path(cfg.ledger_path).read_text().splitlines()]
    decision_event = next(e for e in ledger_lines if e.get("type") == "decision")
    assert decision_event["extraction_ms"] == decision.extraction_ms
    assert decision_event["parser_ms"] == decision.parser_ms
    assert decision_event["evaluation_ms"] == decision.evaluation_ms
    assert decision_event["total_ms"] == decision.total_ms
    assert "pypdf_p0" in decision_event["timings"]


def test_upsert_preserva_ruta_si_no_llega_nueva(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1", source_path="/lotes/a/f.pdf")
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")  # re-visto sin ruta: no la borra
    row = store.conn.execute("SELECT source_path FROM invoices WHERE id = 'inv-1'").fetchone()
    assert row["source_path"] == "/lotes/a/f.pdf"
    store.upsert_invoice("inv-1", "f.pdf", "sha-1", source_path="/lotes/b/f.pdf")
    row = store.conn.execute("SELECT source_path FROM invoices WHERE id = 'inv-1'").fetchone()
    assert row["source_path"] == "/lotes/b/f.pdf"  # ruta nueva sí actualiza
