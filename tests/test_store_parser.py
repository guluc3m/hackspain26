from __future__ import annotations

import json

from albertitos.extract.ladder import PageExtraction
from albertitos.parse.parser import parse_fields
from albertitos.store.ledger import Ledger
from albertitos.types import ExtractionFeature, Result


def _feature(texto: str, method: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=method, data=texto, page=0, extractor_version="1")


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
    store.add_field("inv-1", "total", [
        {"extractor": "pypdf", "value": 121.00, "confidence": 0.7},
        {"extractor": "vlm", "value": 120.50, "confidence": 0.9},
    ])
    fields = store.fields_for("inv-1")
    assert len(fields["total"]) == 2
    assert fields["total"][0]["value"] == 120.50  # ordenado por confianza


def test_store_idempotente_feature(store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1")
    kw = {
        "stage": "pypdf", "page": 0, "extractor_version": "1", "config_version": "cfg",
        "sha256": "sha-1", "latency_ms": 5, "confidence": 1.0, "outcome": "pypdf",
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
    store.add_override({
        "invoice_id": "inv-1", "field_type": "iban",
        "before": "ES00", "after": "ES9121000418450200051332",
        "who": "revisor", "rung": "review-ui", "reason": "lectura",
    })
    rows = store.overrides_for("inv-1")
    assert len(rows) == 1
    assert rows[0]["who"] == "revisor"
    assert json.loads(rows[0]["after"]) == "ES9121000418450200051332"
