from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
from pypdf import PdfWriter

from filemaid.extract.cache import FeatureCache
from filemaid.extract.ladder import PageExtraction
from filemaid.extract.rungs import firecrawl, typesafe_jev
from filemaid.extract.rungs.context import PageContext
from filemaid.parse import extractors, normalizers, parser
from filemaid.rules.config import RuleConfig
from filemaid.rules.engine import evaluate
from filemaid.rules.master import MasterData, Pedido, Proveedor
from filemaid.types import Candidate, ExtractionFeature, ExtractionField, Result, RuleVerdict


def _create_dummy_pdf(path: Path) -> Path:
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with open(path, "wb") as f:
        writer.write(f)
    return path


def _create_context(
    tmp_path: Path,
    config: dict | None = None,
    sha: str = "sha_adversarial_test",
    ocr_text: str = "",
) -> PageContext:
    pdf_path = _create_dummy_pdf(tmp_path / "invoice.pdf")
    cache = FeatureCache(tmp_path / "cache")
    return PageContext(
        pdf_path=pdf_path,
        page_index=0,
        cache=cache,
        config=config or {},
        page_image_sha=sha,
        ocr_text=ocr_text,
    )


# ==============================================================================
# 1. TypeSafe System One Rung Adversarial Attacks
# ==============================================================================


def test_typesafe_http_401_403_degrades_to_skipped(tmp_path: Path):
    """TypeSafe unauthorized / forbidden responses degrade cleanly without crashing."""
    ctx = _create_context(tmp_path, {"typesafe_api_key": "bad_key"}, ocr_text="Factura B12345678")

    def mock_401(*args, **kwargs):
        req = httpx.Request("POST", "https://api.typesafe.ai/v1/systemone")
        return httpx.Response(401, json={"error": "Unauthorized"}, request=req)

    with patch("httpx.post", side_effect=mock_401):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method == "skipped:typesafe-error:HTTPStatusError"
    assert feat.latency_ms >= 0


def test_typesafe_timeout_degrades_to_skipped(tmp_path: Path):
    """TypeSafe gateway timeout degrades cleanly to skipped:typesafe-error:ReadTimeout."""
    ctx = _create_context(tmp_path, {"typesafe_api_key": "valid_key"}, ocr_text="Factura B12345678")

    def mock_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Connection timed out")

    with patch("httpx.post", side_effect=mock_timeout):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method == "skipped:typesafe-error:ReadTimeout"
    assert feat.latency_ms >= 0


def test_typesafe_malformed_json_degrades_to_skipped(tmp_path: Path):
    """TypeSafe non-JSON / broken payload degrades cleanly to skipped."""
    ctx = _create_context(tmp_path, {"typesafe_api_key": "valid_key"}, ocr_text="Factura B12345678")

    def mock_corrupt(*args, **kwargs):
        req = httpx.Request("POST", "https://api.typesafe.ai/v1/systemone")
        return httpx.Response(200, text="<!DOCTYPE html><html>502 Bad Gateway</html>", request=req)

    with patch("httpx.post", side_effect=mock_corrupt):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method.startswith("skipped:typesafe-error:")
    assert feat.latency_ms >= 0


def test_typesafe_malformed_schema_missing_questions_degrades_to_skipped(tmp_path: Path):
    """TypeSafe response returning valid JSON but missing requested typed questions."""
    ctx = _create_context(tmp_path, {"typesafe_api_key": "valid_key"}, ocr_text="Factura B12345678")

    def mock_bad_schema(*args, **kwargs):
        req = httpx.Request("POST", "https://api.typesafe.ai/v1/systemone")
        return httpx.Response(200, json={"model": "jev-latest", "answers": {}}, request=req)

    with patch("httpx.post", side_effect=mock_bad_schema):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method == "skipped:typesafe-malformed-response"
    assert feat.latency_ms >= 0


# ==============================================================================
# 2. Firecrawl Rung Adversarial Attacks
# ==============================================================================


def test_firecrawl_http_429_rate_limit_degrades_to_skipped(tmp_path: Path):
    """Firecrawl rate limits degrade cleanly to skipped:firecrawl-error:HTTPStatusError."""
    ctx = _create_context(tmp_path, {"firecrawl_api_key": "fc_key"})

    def mock_429(*args, **kwargs):
        req = httpx.Request("POST", "https://api.firecrawl.dev/v2/parse")
        return httpx.Response(429, text="Too Many Requests", request=req)

    with patch("httpx.post", side_effect=mock_429):
        feat = firecrawl.extract(ctx)

    assert feat.extraction_method == "skipped:firecrawl-error:HTTPStatusError"
    assert feat.latency_ms >= 0


def test_firecrawl_timeout_degrades_to_skipped(tmp_path: Path):
    """Firecrawl network connection timeout degrades cleanly to skipped."""
    ctx = _create_context(tmp_path, {"firecrawl_api_key": "fc_key"})

    def mock_to(*args, **kwargs):
        raise httpx.ReadTimeout("Firecrawl read timeout")

    with patch("httpx.post", side_effect=mock_to):
        feat = firecrawl.extract(ctx)

    assert feat.extraction_method == "skipped:firecrawl-error:ReadTimeout"
    assert feat.latency_ms >= 0


def test_firecrawl_empty_or_whitespace_markdown_degrades_to_skipped(tmp_path: Path):
    """Firecrawl returning empty markdown degrades to skipped:firecrawl-empty."""
    ctx = _create_context(tmp_path, {"firecrawl_api_key": "fc_key"})

    def mock_empty(*args, **kwargs):
        req = httpx.Request("POST", "https://api.firecrawl.dev/v2/parse")
        return httpx.Response(200, json={"data": {"markdown": "   \n\t  "}}, request=req)

    with patch("httpx.post", side_effect=mock_empty):
        feat = firecrawl.extract(ctx)

    assert feat.extraction_method == "skipped:firecrawl-empty"
    assert feat.latency_ms >= 0


# ==============================================================================
# 3. Extractors & Normalizers Adversarial Attacks
# ==============================================================================


def test_extractors_markdown_tables_with_pipe_separators():
    """Markdown tables produced by Firecrawl with pipe separators must extract properly."""
    markdown_doc = '''
# Factura F-2026-001

| Campo | Valor |
| --- | --- |
| Proveedor | Suministros Rapidos S.L. |
| NIF | B12345678 |
| Cliente | Banco Miralmar S.A. |
| CIF | A58231074 |
| Fecha emisión | 15/02/2026 |
| Pedido | PO-2026-0099 |
| Base Imponible | 1.000,00 € |
| IVA 21% | 210,00 € |
| Total Factura | 1.210,00 € |
'''
    val_nif, conf_nif = extractors._nif(markdown_doc)
    assert val_nif == "B12345678"

    val_fecha, conf_fecha = extractors._fecha(markdown_doc)
    assert val_fecha == "15/02/2026"

    val_pedido, conf_pedido = extractors._pedido(markdown_doc)
    assert val_pedido == "PO-2026-0099"

    val_base, conf_base = extractors._base(markdown_doc)
    assert val_base == 1000.0

    val_total, conf_total = extractors._total(markdown_doc)
    assert val_total == 1210.0


def test_extractors_vendor_nif_preferred_over_client_cif_even_when_inverted():
    """Vendor NIF is selected over known or labeled client CIF regardless of line order."""
    doc_order_1 = '''
Cliente: Banco Miralmar S.A. CIF: A58231074
Proveedor: Limpiezas Turia S.L. NIF: B80233808
'''
    val1, conf1 = extractors._nif(doc_order_1)
    assert val1 == "B80233808"

    doc_order_2 = '''
Proveedor: Limpiezas Turia S.L. NIF: B80233808
Cliente: Banco Miralmar S.A. CIF: A58231074
'''
    val2, conf2 = extractors._nif(doc_order_2)
    assert val2 == "B80233808"


def test_normalizers_parse_amount_thousands_and_ocr_artifacts():
    """parse_amount handles million with commas, OCR dropped dot, and OCR double comma."""
    assert normalizers.parse_amount("1,000,000") == 1000000.0
    assert normalizers.parse_amount("1.000.000") == 1000000.0
    assert normalizers.parse_amount("1,000,000.50") == 1000000.50
    assert normalizers.parse_amount("1.000.000,50") == 1000000.50
    assert normalizers.parse_amount("1.29288") == 1292.88
    assert normalizers.parse_amount("1,135,20") == 1135.20


# ==============================================================================
# 4. End-to-End Rule Engine Adversarial Invariants
# ==============================================================================


def test_rule_engine_never_pays_on_corrupted_or_inconsistent_extractions():
    """Any discrepancy (IBAN mismatch, total mismatch, unregistered supplier) resolves to NO_PAGAR."""
    master = MasterData(
        proveedores={"B12345678": Proveedor("B12345678", "Proveedor Test", "ES9121000418450200051332")},
        pedidos={"PO-2026-0001": Pedido("PO-2026-0001", "B12345678", 121.0, estado="PENDIENTE", pagado=False)},
    )
    cfg = RuleConfig({"outcomes": {"default": "NO_PAGAR"}}, source_sha="sha_test")

    # Inconsistent total: base 100 + iva 21 != total 150
    corrupted_fields = {
        "nif": ExtractionField(type="nif", values=[Candidate("regex_nif", "B12345678", 0.85)]),
        "iban": ExtractionField(type="iban", values=[Candidate("regex_iban", "ES9121000418450200051332", 0.9)]),
        "total": ExtractionField(type="total", values=[Candidate("regex_total", 150.0, 0.7)]),
        "base": ExtractionField(type="base", values=[Candidate("regex_base", 100.0, 0.6)]),
        "iva_rate": ExtractionField(type="iva_rate", values=[Candidate("regex_iva_rate", 21, 0.6)]),
        "iva_amount": ExtractionField(type="iva_amount", values=[Candidate("regex_iva_amount", 21.0, 0.6)]),
        "fecha": ExtractionField(type="fecha", values=[Candidate("regex_fecha", "15/01/2026", 0.7)]),
        "pedido": ExtractionField(type="pedido", values=[Candidate("regex_pedido", "PO-2026-0001", 0.7)]),
    }

    decision = evaluate(corrupted_fields, master, cfg, "inv_bad", "file_bad.pdf")
    assert decision.result == Result.NO_PAGAR
    totals_ev = next(e for e in decision.rule_evaluations if e.code == "TOTALS_MUST_MATCH")
    assert totals_ev.verdict == RuleVerdict.FAIL
