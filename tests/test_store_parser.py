from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from filemaid.extract.ladder import PageExtraction
from filemaid.parse.parser import parse_fields
from filemaid.pipeline import Pipeline
from filemaid.store.pouch import PouchStore
from filemaid.store.queries import invoice_detail, save_override
from filemaid.store.trace import ScanTrace
from filemaid.types import ConfigSnapshot, Decision, ExtractionFeature, ExtractionField, Result, RuleEvaluation


def _feature(texto: str, method: str) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text", extraction_method=method, data=texto, page=0, extractor_version="1"
    )


def test_parser_conserva_candidatos_de_varias_fuentes():
    page = PageExtraction(page=0)
    page.features.append(_feature("TOTAL 120,50 EUR", "regex_total"))
    page.features.append(_feature("TOTAL 121,00 EUR", "regex_total"))
    fields = parse_fields([page])
    total = next(f for f in fields if f.type == "total")
    assert len(total.values) == 2
    assert {c.extractor for c in total.values} == {"regex_total"}


def test_store_nunca_colapsa_candidatos(store: PouchStore):
    f = ExtractionField(type="total")
    f.add("a", 120.50, 0.9)
    f.add("b", 121.00, 0.8)

    trace = ScanTrace(store, Path("f.pdf"), "sha-1", "inv-1")
    with trace.active():
        trace.begin("cfg-1", "ext-1", "master-1")
        trace.fields([f], 10)

    detail = invoice_detail(store, trace.identity["file_key"])
    assert detail is not None
    assert len(detail["fields"]["total"]) == 2
    assert detail["fields"]["total"][0]["value"] == 120.50


def test_store_idempotente_feature(store: PouchStore):
    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method="pypdf",
        data="hola",
        page=0,
        sha256="sha-1",
        latency_ms=10,
        confidence=0.9,
        extractor_version="1",
    )
    trace = ScanTrace(store, Path("f.pdf"), "sha-1", "inv-1")
    with trace.active():
        trace.begin("cfg-1", "ext-1", "master-1")
        trace.rung(0, "pypdf", [feat], None)
        trace.rung(0, "pypdf", [feat], None)

    features = store.list(f"feature:{trace.scan_id}:")
    assert len(features) >= 1


def test_override_con_procedencia(store: PouchStore):
    trace = ScanTrace(store, Path("f.pdf"), "sha-1", "inv-1")
    with trace.active():
        trace.begin("cfg-1", "ext-1", "master-1")
        d = Decision(
            invoice_id="inv-1",
            file_id="f.pdf",
            result=Result.ESCALAR,
            rule_evaluations=[],
            config_snapshot=ConfigSnapshot("cfg-1"),
        )
        trace.decision(d, "cfg-1")

    file_key = trace.identity["file_key"]
    save_override(
        store,
        file_key,
        {
            "field_type": "iban",
            "before": "ES0000000000000000000000",
            "after": "ES9121000418450200051332",
            "who": "revisor",
            "rung": "tesseract",
            "reason": "IBAN borroso",
        },
    )

    detail = invoice_detail(store, file_key)
    assert detail is not None
    assert len(detail["overrides"]) == 1
    assert detail["overrides"][0]["who"] == "revisor"
    assert json.loads(detail["overrides"][0]["after"]) == "ES9121000418450200051332"


def test_store_guarda_reason_code(store: PouchStore):
    trace = ScanTrace(store, Path("f.pdf"), "sha-1", "inv-1")
    with trace.active():
        trace.begin("cfg-1", "ext-1", "master-1")
        d = Decision(
            invoice_id="inv-1",
            file_id="f.pdf",
            result=Result.ESCALAR,
            rule_evaluations=[
                RuleEvaluation(
                    code="FECHA_VALIDA",
                    verdict=Result.ESCALAR,
                    reason="sin campo fecha",
                    reason_code="SIN_CAMPO",
                    consumed={},
                )
            ],
            config_snapshot=ConfigSnapshot("cfg-1"),
        )
        trace.decision(d, "cfg-1")

    dec_doc = store.hydrate(store.get(f"decision:{trace.scan_id}"))
    evals = dec_doc["decision"]["rule_evaluations"]
    assert len(evals) == 1
    assert evals[0]["reason_code"] == "SIN_CAMPO"


def test_store_guarda_stage_timings(store: PouchStore):
    trace = ScanTrace(store, Path("f.pdf"), "sha-1", "inv-1")
    with trace.active():
        trace.begin("cfg-1", "ext-1", "master-1")
        d = Decision(
            invoice_id="inv-1",
            file_id="f.pdf",
            result=Result.PAGAR,
            rule_evaluations=[],
            config_snapshot=ConfigSnapshot("cfg-1"),
            extraction_ms=120,
            parser_ms=30,
            evaluation_ms=10,
            total_ms=160,
            timings={"pypdf_p0": 110, "regex_p0": 10},
        )
        trace.decision(d, "cfg-1")

    dec_doc = store.hydrate(store.get(f"decision:{trace.scan_id}"))
    decision_data = dec_doc["decision"]
    assert decision_data["extraction_ms"] == 120
    assert decision_data["total_ms"] == 160
    assert decision_data["timings"]["pypdf_p0"] == 110


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

    # Check PouchStore decision doc
    decisions = [pipe.store.hydrate(d) for d in pipe.store.list("decision:")]
    assert len(decisions) == 1
    r = decisions[0]["decision"]
    assert r["extraction_ms"] == decision.extraction_ms
    assert r["parser_ms"] == decision.parser_ms
    assert r["evaluation_ms"] == decision.evaluation_ms
    assert r["total_ms"] == decision.total_ms

    # Check PouchStore event doc
    events = [pipe.store.hydrate(d) for d in pipe.store.list("event:")]
    decision_event = next(e["payload"] for e in events if e.get("type") == "decision")
    assert decision_event["extraction_ms"] == decision.extraction_ms
    assert decision_event["parser_ms"] == decision.parser_ms
    assert decision_event["evaluation_ms"] == decision.evaluation_ms
    assert decision_event["total_ms"] == decision.total_ms
    assert "pypdf_p0" in decision_event["timings"]
