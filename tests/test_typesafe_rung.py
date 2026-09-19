from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from filemaid.extract.cache import FeatureCache
from filemaid.extract.rungs import typesafe_jev
from filemaid.extract.rungs.context import PageContext


@pytest.fixture
def ctx(tmp_path: Path) -> PageContext:
    return PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=FeatureCache(tmp_path / "cache"),
        config={"typesafe_api_key": "test-key", "config_version": "cfg-1"},
        page_image_sha="page-sha",
        ocr_text="FACTURA. Total: 121,00 EUR. NIF: B12345678.",
    )


@pytest.fixture
def response() -> dict:
    return {
        "model": "jev-2026-09-15",
        "usage": {"input_tokens": 120, "output_tokens": 12},
        "answers": {
            "is_invoice": {"type": "noul", "noul": 0.98},
            "has_fiscal_data": {"type": "noul", "noul": 0.95},
            "document_quality": {
                "type": "score", "score": 1.8, "confidence": 0.9,
                "legend": {"0": "Ilegible", "1": "Parcial", "2": "Legible"},
                "probabilities": {"0": 0.0, "1": 0.2, "2": 0.8},
            },
            "document_category": {
                "type": "choice", "choice": "invoice", "confidence": 0.99,
                "probabilities": {"invoice": 0.99, "receipt": 0.005, "other": 0.005},
            },
        },
    }


def test_missing_prerequisites_do_not_request(ctx, monkeypatch):
    def unexpected_request(*args, **kwargs):
        pytest.fail("Missing input must not reach the provider")

    monkeypatch.setattr(httpx, "post", unexpected_request)
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    ctx.config.clear()
    assert typesafe_jev.extract(ctx).extraction_method == "skipped:no-typesafe-api-key"
    ctx.config["typesafe_api_key"] = "test-key"
    ctx.config["ocr_text"] = "Global hint must not leak between pages"
    ctx.ocr_text = " \n "
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:typesafe-no-ocr-text"
    assert feat.latency_ms >= 0
    ctx.page_image_sha = None
    assert typesafe_jev.extract(ctx).extraction_method == "skipped:no-page-image"


def test_typed_evidence_is_cached_without_invoice_field_generation(ctx, response, monkeypatch):
    from filemaid.extract.ladder import PageExtraction
    from filemaid.parse.parser import parse_fields

    calls = []
    ctx.config.update({
        "typesafe_api_url": "https://api.typesafe.ai/v1/systemone",
        "typesafe_model": "jev-latest",
        "rungs": {"typesafe_jev": {"endpoint": "https://custom.test/judge", "model": "custom-model"}},
    })

    def mock_post(url, headers, json, timeout):
        calls.append(url)
        assert url == "https://custom.test/judge"
        assert json["model"] == "custom-model"
        assert json["state"] == {"ocr_text": ctx.ocr_text, "page_index": 0}
        assert {key: value["type"] for key, value in json["questions"].items()} == {
            "is_invoice": "noul", "has_fiscal_data": "noul",
            "document_quality": "score", "document_category": "choice",
        }
        assert isinstance(json["questions"]["document_quality"]["criteria"], list)
        assert isinstance(json["questions"]["document_category"]["criteria"], dict)
        return httpx.Response(200, json=response, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = typesafe_jev.extract(ctx)
    assert feat.type == "typed_evidence"
    assert feat.extraction_method == "typesafe_jev"
    assert feat.data == response
    assert 0.0 <= feat.confidence <= 1.0
    assert feat.latency_ms >= 0
    assert parse_fields([PageExtraction(page=0, features=[feat])]) == []
    assert typesafe_jev.extract(ctx).data == response
    assert len(calls) == 1


@pytest.mark.parametrize("status", [401, 429, 500])
def test_http_errors_are_not_cached(ctx, monkeypatch, status):
    def mock_post(url, **kwargs):
        return httpx.Response(status, text="Provider error", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:typesafe-error:HTTPStatusError"
    assert feat.latency_ms >= 0
    assert ctx.cache.get(ctx.page_image_sha, typesafe_jev.VERSION, "cfg-1") is None


def test_timeout_is_recorded(ctx, monkeypatch):
    def mock_post(*args, **kwargs):
        raise httpx.ConnectTimeout("Provider unavailable")

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:typesafe-error:ConnectTimeout"
    assert feat.latency_ms >= 0


@pytest.mark.parametrize("payload", [[], {}, {"answers": {}}, {"answers": "TOTAL: 999 EUR"}])
def test_malformed_response_does_not_produce_text(ctx, monkeypatch, payload):
    def mock_post(url, **kwargs):
        return httpx.Response(200, json=payload, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:typesafe-malformed-response"
    assert feat.data == ""
    assert feat.latency_ms >= 0


def test_invalid_json_skips_without_caching(ctx, monkeypatch):
    def mock_post(url, **kwargs):
        return httpx.Response(200, text="not JSON", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:typesafe-error:JSONDecodeError"
    assert ctx.cache.get(ctx.page_image_sha, typesafe_jev.VERSION, "cfg-1") is None
