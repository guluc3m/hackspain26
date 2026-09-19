from __future__ import annotations

import pytest

from filemaid.types import Candidate, Decision, ExtractionField, Result, RuleVerdict


def test_resultado_solo_tres_valores():
    assert {r.value for r in Result} == {"PAGAR", "NO_PAGAR", "ESCALAR"}


def test_veredicto_tres_valores():
    assert {v.value for v in RuleVerdict} == {"PASS", "FAIL", "UNKNOWN"}


def test_campo_conserva_todos_los_candidatos():
    f = ExtractionField(type="total")
    f.add("regex_total", 121.00, 0.7)
    f.add("vlm", 120.00, 0.9)
    assert len(f.values) == 2
    assert {c.extractor for c in f.values} == {"regex_total", "vlm"}


def test_confianza_fuera_de_rango_se_rechaza():
    f = ExtractionField(type="nif")
    f.add("regex", "B12345678", 1.5)
    f.add("regex", "B12345678", -0.1)
    assert f.values == []


def test_candidate_campos_del_contrato():
    c = Candidate(extractor="tesseract", value="hola", confidence=0.5)
    assert c.extractor == "tesseract" and c.confidence == 0.5


@pytest.mark.parametrize("tipo", ["nif", "iban", "total", "iva_amount", "fecha", "pedido"])
def test_tipos_de_campo_esperados(tipo: str):
    f = ExtractionField(type=tipo)
    assert f.type == tipo

def test_decision_timings_fields():
    d = Decision(
        invoice_id="inv-1",
        file_id="a.pdf",
        result=Result.PAGAR,
        extraction_ms=100,
        parser_ms=10,
        evaluation_ms=5,
        total_ms=115,
        timings={"extraction_ms": 100, "parser_ms": 10, "evaluation_ms": 5, "total_ms": 115},
    )
    assert d.extraction_ms == 100
    assert d.parser_ms == 10
    assert d.evaluation_ms == 5
    assert d.total_ms == 115
    assert d.timings["extraction_ms"] == 100
