from __future__ import annotations

import base64
from pathlib import Path
import pytest
import httpx

from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.rungs import typesafe_jev
from filemaid.extract.rungs.context import PageContext


def _dummy_png() -> bytes:
    # 1x1 valid PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


def test_skip_no_page_image(tmp_path: Path):
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={"typesafe_api_key": "test-key"},
        page_image_sha=None,
    )
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:no-page-image"
    assert feat.extractor_version == typesafe_jev.VERSION


def test_skip_no_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={},
        page_image_sha="sha123",
    )
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:no-typesafe-api-key"
    assert feat.extractor_version == typesafe_jev.VERSION


def test_skip_no_page_png(tmp_path: Path):
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={"typesafe_api_key": "ts-test"},
        pages_dir=tmp_path / "pages",
        page_image_sha="sha123",
    )
    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:no-page-png"


def test_typesafe_successful_extraction_and_cache(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "typesafe_api_key": "ts-mock-key",
        "typesafe_api_url": "https://api.typesafe.ai/v1/systemone",
        "typesafe_model": "jev-latest",
        "config_version": "v1.0",
        "ocr_text": "Texto previo",
    }
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config=config,
        pages_dir=pages_dir,
        page_image_sha=page_sha,
    )

    requested_urls = []
    requested_bodies = []

    def mock_post(url, headers, json, timeout):
        requested_urls.append(str(url))
        requested_bodies.append(json)
        assert headers["Authorization"] == "Bearer ts-mock-key"
        resp_payload = {
            "answers": {
                "is_valid_invoice": {"value": True, "confidence": 0.95},
                "nif": {"value": "B12345678", "confidence": 0.90},
                "iban": {"value": "ES1234567890123456789012", "confidence": 0.88},
                "total": {"value": "121.50 EUR", "confidence": 0.92},
                "fecha": {"value": "2026-01-15", "confidence": 0.85},
                "pedido": {"value": "PED-2026-001", "confidence": 0.80},
                "iva": {"value": "21.00 EUR", "confidence": 0.85},
            }
        }
        req = httpx.Request("POST", str(url), headers=headers, json=json)
        return httpx.Response(200, json=resp_payload, request=req)

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "typesafe_jev"
    assert "NIF: B12345678" in feat.data
    assert "IBAN: ES1234567890123456789012" in feat.data
    assert "TOTAL: 121.50 EUR" in feat.data
    assert feat.page == 0
    assert feat.sha256 == page_sha
    assert feat.extractor_version == typesafe_jev.VERSION
    assert feat.latency_ms >= 0
    assert feat.confidence >= 0.8

    # Verify HTTP request payload
    assert requested_urls == ["https://api.typesafe.ai/v1/systemone"]
    assert requested_bodies[0]["model"] == "jev-latest"
    assert "image" in requested_bodies[0]["state"]
    assert requested_bodies[0]["state"]["ocr_text"] == "Texto previo"
    assert "questions" in requested_bodies[0]
    assert "nif" in requested_bodies[0]["questions"]
    assert "total" in requested_bodies[0]["questions"]

    # Test caching: second call returns cached result without hitting network
    cached_feat = typesafe_jev.extract(ctx)
    assert cached_feat.extraction_method == "typesafe_jev"
    assert cached_feat.data == feat.data
    assert len(requested_urls) == 1


def test_typesafe_http_error_graceful_skip(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "typesafe_api_key": "ts-error-key",
        "config_version": "v1.0",
    }
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config=config,
        pages_dir=pages_dir,
        page_image_sha=page_sha,
    )

    def mock_post(url, headers, json, timeout):
        raise httpx.ConnectTimeout("Connection timeout to typesafe.ai")

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method.startswith("skipped:typesafe-error:")
    assert feat.extractor_version == typesafe_jev.VERSION
    assert feat.latency_ms >= 0


def test_typesafe_empty_answers_returns_skip(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "typesafe_api_key": "ts-empty-key",
        "config_version": "v1.0",
    }
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config=config,
        pages_dir=pages_dir,
        page_image_sha=page_sha,
    )

    def mock_post(url, headers, json, timeout):
        req = httpx.Request("POST", str(url), headers=headers, json=json)
        return httpx.Response(200, json={"answers": {}}, request=req)

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = typesafe_jev.extract(ctx)
    assert feat.extraction_method == "skipped:typesafe-empty"
    assert feat.extractor_version == typesafe_jev.VERSION
    assert feat.latency_ms >= 0
