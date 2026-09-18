"""Baseline smoke test — the skeleton imports and the contract types hold."""

from albertitos.types import Candidate, ExtractionFeature, ExtractionField, RuleVerdict


def test_contract_types_exist():
    f = ExtractionFeature(type="pdf_text", extraction_method="pypdf", timestamp=0.0, data="hola")
    fld = ExtractionField(type="nif", timestamp=0.0, values=[Candidate("pypdf", "B46102331", 0.9)])
    v = RuleVerdict(code="NIF_IN_MASTER", outcome="PASS", reason="ok", consumed={})
    assert f.type == "pdf_text"
    assert fld.values[0].confidence == 0.9
    assert v.outcome == "PASS"
