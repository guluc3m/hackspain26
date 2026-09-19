from __future__ import annotations

import base64
import json
import math
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from filemaid.config import AppConfig
from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.ladder import PageExtraction, extract_file
from filemaid.extract.rungs import cloud_vlm, typesafe_jev
from filemaid.extract.rungs.context import PageContext
from filemaid.pipeline import Pipeline
from filemaid.types import Decision, ExtractionFeature, Result


def _dummy_png() -> bytes:
    # Valid 1x1 PNG image bytes
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


def _setup_context(tmp_path: Path, config: dict | None = None, sha: str = "img_sha_1") -> PageContext:
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "invoice.pdf",
        page_index=0,
        cache=cache,
        config=config or {},
        pages_dir=pages_dir,
        page_image_sha=sha,
    )
    return ctx


# ==============================================================================
# Adversarial Attack: TypeSafe System One Rung
# ==============================================================================


def test_typesafe_malformed_missing_answers(tmp_path: Path):
    """Attack TypeSafe rung with response missing 'answers' and 'results' fields."""
    ctx = _setup_context(tmp_path, {"typesafe_api_key": "test_key"}, sha="ts_no_answers")

    def mock_response(request: httpx.Request):
        return httpx.Response(200, json={"status": "success", "data": "unexpected_schema"})

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method == "skipped:typesafe-empty"
    assert feat.latency_ms >= 0
    assert feat.data == ""


def test_typesafe_malformed_non_dict_json_array(tmp_path: Path):
    """Attack TypeSafe rung with a top-level JSON array instead of a JSON object."""
    ctx = _setup_context(tmp_path, {"typesafe_api_key": "test_key"}, sha="ts_json_array")

    def mock_response(request: httpx.Request):
        return httpx.Response(200, json=["unexpected", "list", "response"])

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = typesafe_jev.extract(ctx)

    # Should not crash with AttributeError, graceful skip with latency measured
    assert feat.extraction_method.startswith("skipped:")
    assert feat.latency_ms >= 0


def test_typesafe_malformed_non_numeric_probabilities_and_confidences(tmp_path: Path):
    """Attack TypeSafe confidence calculator with non-numeric, NaN, and Inf values."""
    ctx = _setup_context(tmp_path, {"typesafe_api_key": "test_key"}, sha="ts_nan_prob")

    def mock_response(request: httpx.Request):
        raw_payload = (
            '{"answers": {'
            '"nif": {"value": "B12345678", "confidence": "non_numeric"}, '
            '"iban": {"value": "ES9121000418450200051332", "confidence": NaN}, '
            '"total": {"value": "150.00", "confidence": Infinity}, '
            '"fecha": {"value": "2026-01-01", "probabilities": {"valid": "high", "invalid": "low"}}'
            '}}'
        )
        return httpx.Response(200, text=raw_payload, headers={"Content-Type": "application/json"})

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = typesafe_jev.extract(ctx)

    # Handled without NaN/Inf crashing or corrupting features
    assert feat.confidence is not None
    assert not math.isnan(feat.confidence)
    assert not math.isinf(feat.confidence)
    assert 0.0 <= feat.confidence <= 1.0
    assert feat.latency_ms >= 0


def test_typesafe_http_429_rate_limit(tmp_path: Path):
    """Attack TypeSafe rung with HTTP 429 Too Many Requests."""
    ctx = _setup_context(tmp_path, {"typesafe_api_key": "test_key"}, sha="ts_429")

    def mock_response(request: httpx.Request):
        return httpx.Response(429, text="Rate limit exceeded")

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method == "skipped:typesafe-error:HTTPStatusError"
    assert feat.latency_ms >= 0


def test_typesafe_network_timeout(tmp_path: Path):
    """Attack TypeSafe rung with connection/read timeout."""
    ctx = _setup_context(tmp_path, {"typesafe_api_key": "test_key"}, sha="ts_timeout")

    def mock_response(request: httpx.Request):
        raise httpx.ReadTimeout("TypeSafe API read timeout")

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = typesafe_jev.extract(ctx)

    assert feat.extraction_method == "skipped:typesafe-error:ReadTimeout"
    assert feat.latency_ms >= 0


# ==============================================================================
# Adversarial Attack: OpenAI-compatible Cloud VLM Rung
# ==============================================================================


def test_cloud_vlm_malformed_empty_choices(tmp_path: Path):
    """Attack Cloud VLM with empty choices list []."""
    ctx = _setup_context(tmp_path, {"openai_api_key": "test_key"}, sha="cv_empty_choices")

    def mock_response(request: httpx.Request):
        return httpx.Response(200, json={"choices": []})

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = cloud_vlm.extract(ctx)

    assert feat.extraction_method == "skipped:cloud-vlm-error:IndexError"
    assert feat.latency_ms >= 0


def test_cloud_vlm_malformed_missing_choices_key(tmp_path: Path):
    """Attack Cloud VLM with missing 'choices' key in payload."""
    ctx = _setup_context(tmp_path, {"openai_api_key": "test_key"}, sha="cv_no_choices")

    def mock_response(request: httpx.Request):
        return httpx.Response(200, json={"id": "chat-123", "object": "chat.completion"})

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = cloud_vlm.extract(ctx)

    assert feat.extraction_method == "skipped:cloud-vlm-error:KeyError"
    assert feat.latency_ms >= 0


def test_cloud_vlm_malformed_content_none_or_empty(tmp_path: Path):
    """Attack Cloud VLM with choices message content None or whitespace."""
    ctx = _setup_context(tmp_path, {"openai_api_key": "test_key"}, sha="cv_none_content")

    def mock_response(request: httpx.Request):
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None}}]})

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = cloud_vlm.extract(ctx)

    assert feat.extraction_method == "skipped:cloud-vlm-empty"
    assert feat.latency_ms >= 0


def test_cloud_vlm_http_500_status(tmp_path: Path):
    """Attack Cloud VLM with HTTP 500 server error."""
    ctx = _setup_context(tmp_path, {"openai_api_key": "test_key"}, sha="cv_500")

    def mock_response(request: httpx.Request):
        return httpx.Response(500, text="Internal Server Error")

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = cloud_vlm.extract(ctx)

    assert feat.extraction_method == "skipped:cloud-vlm-error:HTTPStatusError"
    assert feat.latency_ms >= 0


def test_cloud_vlm_http_429_rate_limit(tmp_path: Path):
    """Attack Cloud VLM with HTTP 429 rate limit."""
    ctx = _setup_context(tmp_path, {"openai_api_key": "test_key"}, sha="cv_429")

    def mock_response(request: httpx.Request):
        return httpx.Response(429, text="Rate Limit Exceeded")

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = cloud_vlm.extract(ctx)

    assert feat.extraction_method == "skipped:cloud-vlm-error:HTTPStatusError"
    assert feat.latency_ms >= 0


def test_cloud_vlm_network_timeout(tmp_path: Path):
    """Attack Cloud VLM with timeout exception."""
    ctx = _setup_context(tmp_path, {"openai_api_key": "test_key"}, sha="cv_timeout")

    def mock_response(request: httpx.Request):
        raise httpx.ConnectTimeout("OpenAI gateway connection timed out")

    transport = httpx.MockTransport(mock_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = cloud_vlm.extract(ctx)

    assert feat.extraction_method == "skipped:cloud-vlm-error:ConnectTimeout"
    assert feat.latency_ms >= 0


# ==============================================================================
# Adversarial Attack: Pipeline Resilience and Stage Metrics Integrity
# ==============================================================================


def _setup_app_config(tmp_path: Path) -> AppConfig:
    root = tmp_path / "app_data"
    root.mkdir(parents=True, exist_ok=True)
    master_d = tmp_path / "master"
    master_d.mkdir(parents=True, exist_ok=True)
    rules_p = master_d / "rules.yaml"

    # Master files minimal setup
    (master_d / "proveedores.json").write_text("[]", encoding="utf-8")
    (master_d / "pedidos.json").write_text("[]", encoding="utf-8")
    (master_d / "facturas_historicas.json").write_text("[]", encoding="utf-8")
    rules_p.write_text(
        """version: "adversarial-test"
tolerance:
  days: 30
  amount_ratio: 0.05
escalation:
  require_qr: false
""",
        encoding="utf-8",
    )

    cfg = AppConfig(root)
    cfg.master_dir = master_d
    cfg.rules_config_path = rules_p
    return cfg


def test_pipeline_never_crashes_mid_batch_on_api_adversities(tmp_path: Path):
    """Batch run containing files where some fail catastrophically and some succeed.
    Verifies that pipeline never halts mid-batch, records clean skipped/error features
    with latency, and produces outcomes.jsonl with all decisions."""
    cfg = _setup_app_config(tmp_path)
    lote_dir = tmp_path / "lote"
    lote_dir.mkdir(parents=True, exist_ok=True)
    outcomes_path = tmp_path / "outcomes.jsonl"

    f1 = lote_dir / "invoice_1.pdf"
    f2 = lote_dir / "invoice_2.pdf"
    f3 = lote_dir / "invoice_3.pdf"

    f1.write_bytes(b"%PDF-1.4 file1")
    f2.write_bytes(b"%PDF-1.4 file2")
    f3.write_bytes(b"%PDF-1.4 file3")

    # Mock extract_file to simulate different adversarial outcomes per file
    def mock_extract_file(path: Path, cache, config, pages_dir):
        if path.name == "invoice_1.pdf":
            # Hits an external API error that graceful-skips with latency
            feat = ExtractionFeature(
                type="pdf_text",
                extraction_method="skipped:typesafe-error:HTTPStatusError",
                data="",
                page=0,
                latency_ms=125,
            )
            return [PageExtraction(page=0, features=[feat], content="")]
        elif path.name == "invoice_2.pdf":
            # Succeeds via text layer
            feat = ExtractionFeature(
                type="pdf_text",
                extraction_method="pypdf",
                data="FACTURA 002 NIF: B99999999 TOTAL: 50.00 EUR FECHA: 2026-02-01",
                page=0,
                latency_ms=30,
                confidence=0.9,
            )
            return [PageExtraction(page=0, features=[feat], content=str(feat.data))]
        else:
            # File 3 has an unhandled file-level crash
            raise RuntimeError("Corrupted PDF structure")

    pipe = Pipeline(cfg)
    with patch("filemaid.pipeline.extract_file", side_effect=mock_extract_file):
        decisions = pipe.run_lote(lote_dir, outcomes_path)

    # Decisions list should contain processed files (f1, f2)
    assert len(decisions) == 2
    f_names = [d.file_id for d in decisions]
    assert "invoice_1.pdf" in f_names
    assert "invoice_2.pdf" in f_names

    # outcomes.jsonl is written
    assert outcomes_path.is_file()
    outcomes_lines = [json.loads(line) for line in outcomes_path.read_text().splitlines()]
    assert len(outcomes_lines) == 2

    # Ledger recorded the item_error for invoice_3.pdf
    ledger_records = [json.loads(line) for line in cfg.ledger_path.read_text().splitlines()]
    item_errors = [r for r in ledger_records if r.get("type") == "item_error"]
    assert len(item_errors) == 1
    assert item_errors[0]["file_id"] == "invoice_3.pdf"
    assert "RuntimeError" in item_errors[0]["error"]

    # Verify invoice_1 recorded skipped feature in store with latency measured
    features_f1 = pipe.store.features_for(decisions[0].invoice_id)
    assert any(f["outcome"].startswith("skipped:") and f["latency_ms"] == 125 for f in features_f1)


def test_stage_metrics_integrity_and_tolerance(tmp_path: Path):
    """Verify metrics integrity:
    1. extraction_ms >= 0, parser_ms >= 0, evaluation_ms >= 0, total_ms >= 0
    2. extraction_ms + parser_ms + evaluation_ms <= total_ms + tolerance (tolerance = 10ms)
    3. timings dict contains per-rung latencies
    4. SQLite store and Ledger match decision timings exactly
    """
    cfg = _setup_app_config(tmp_path)
    pdf_path = tmp_path / "valid_invoice.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test metrics")

    feat1 = ExtractionFeature(
        type="pdf_text",
        extraction_method="skipped:pypdf-no-text",
        data="",
        page=0,
        latency_ms=15,
        confidence=0.0,
    )
    feat2 = ExtractionFeature(
        type="pdf_text",
        extraction_method="cloud_vlm",
        data="FACTURA 2026/099 NIF: B12345678 TOTAL: 242.00 EUR FECHA: 15/01/2026",
        page=0,
        latency_ms=210,
        confidence=0.95,
    )
    mock_pages = [PageExtraction(page=0, features=[feat1, feat2], content=str(feat2.data))]

    pipe = Pipeline(cfg)
    with patch("filemaid.pipeline.extract_file", return_value=mock_pages):
        decision = pipe.process_pdf(pdf_path)

    # 1. Non-negative metrics
    assert decision.extraction_ms >= 0
    assert decision.parser_ms >= 0
    assert decision.evaluation_ms >= 0
    assert decision.total_ms >= 0

    # 2. Stage metrics sum integrity: extraction + parser + eval <= total + tolerance
    tolerance_ms = 10
    stage_sum = decision.extraction_ms + decision.parser_ms + decision.evaluation_ms
    assert stage_sum <= decision.total_ms + tolerance_ms, (
        f"Sum of stages ({stage_sum}ms) exceeds total ({decision.total_ms}ms) beyond tolerance ({tolerance_ms}ms)"
    )

    # 3. Per-rung latency recorded in timings
    assert "skipped_p0" in decision.timings or "skipped:pypdf-no-text_p0" in decision.timings or any("p0" in k for k in decision.timings)
    assert decision.timings["extraction_ms"] == decision.extraction_ms
    assert decision.timings["parser_ms"] == decision.parser_ms
    assert decision.timings["evaluation_ms"] == decision.evaluation_ms
    assert decision.timings["total_ms"] == decision.total_ms

    # 4. Check SQLite store decision row
    rows = pipe.store.decision_rows_for_run(pipe.rule_config.version)
    assert len(rows) == 1
    db_decision = rows[0]
    assert db_decision["extraction_ms"] == decision.extraction_ms
    assert db_decision["parser_ms"] == decision.parser_ms
    assert db_decision["evaluation_ms"] == decision.evaluation_ms
    assert db_decision["total_ms"] == decision.total_ms

    # 5. Check Ledger record
    ledger_records = [json.loads(line) for line in cfg.ledger_path.read_text().splitlines()]
    decision_events = [r for r in ledger_records if r.get("type") == "decision"]
    assert len(decision_events) == 1
    ledger_dec = decision_events[0]
    assert ledger_dec["extraction_ms"] == decision.extraction_ms
    assert ledger_dec["parser_ms"] == decision.parser_ms
    assert ledger_dec["evaluation_ms"] == decision.evaluation_ms
    assert ledger_dec["total_ms"] == decision.total_ms
    assert ledger_dec["timings"] == decision.timings


# ==============================================================================
# Adversarial Attack: Zero-Second and Boundary Latency Cases
# ==============================================================================


def test_zero_second_latency_metric_boundary_handling(tmp_path: Path):
    """Test that sub-millisecond executions do not cause negative latency or division by zero."""
    ctx = _setup_context(tmp_path, {"typesafe_api_key": "test_key"}, sha="ts_zero_ms")

    # Fast in-memory response that registers 0ms
    def instant_response(request: httpx.Request):
        return httpx.Response(200, json={"answers": {"nif": "B12345678"}})

    transport = httpx.MockTransport(instant_response)
    with patch("httpx.post", side_effect=lambda *args, **kwargs: httpx.Client(transport=transport).post(*args, **kwargs)):
        feat = typesafe_jev.extract(ctx)

    assert feat.latency_ms >= 0
    assert isinstance(feat.latency_ms, int)


def test_pipeline_zero_ms_boundary_integrity(tmp_path: Path):
    """Verify that when extraction, parser, or evaluation take 0ms (due to high speed or resolution),
    the stage metrics remain non-negative, integer, and respect extraction + parser + eval <= total + tolerance."""
    cfg = _setup_app_config(tmp_path)
    pdf_path = tmp_path / "zero_time.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 zero time")

    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method="tesseract",
        data="FACTURA 001 NIF: B12345678 TOTAL: 100 EUR FECHA: 2026-01-01",
        page=0,
        latency_ms=0,
        confidence=0.85,
    )
    mock_pages = [PageExtraction(page=0, features=[feat], content=str(feat.data))]

    pipe = Pipeline(cfg)
    with patch("filemaid.pipeline.extract_file", return_value=mock_pages):
        decision = pipe.process_pdf(pdf_path)

    assert decision.extraction_ms >= 0
    assert decision.parser_ms >= 0
    assert decision.evaluation_ms >= 0
    assert decision.total_ms >= 0
    assert decision.extraction_ms + decision.parser_ms + decision.evaluation_ms <= decision.total_ms + 10
