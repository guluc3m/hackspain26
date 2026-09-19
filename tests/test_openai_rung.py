from __future__ import annotations

import base64
from pathlib import Path

import httpx

from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.rungs import cloud_vlm
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
        config={"cloud_api_key": "test-key"},
        page_image_sha=None,
    )
    feat = cloud_vlm.extract(ctx)
    assert feat.extraction_method == "skipped:no-page-image"
    assert feat.extractor_version == cloud_vlm.VERSION


def test_skip_no_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("FILEMAID_CLOUD_API_KEY", raising=False)
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={},
        page_image_sha="sha123",
    )
    feat = cloud_vlm.extract(ctx)
    assert feat.extraction_method == "skipped:no-api-key"
    assert feat.extractor_version == cloud_vlm.VERSION


def test_skip_no_page_png(tmp_path: Path):
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={"cloud_api_key": "sk-test"},
        pages_dir=tmp_path / "pages",
        page_image_sha="sha123",
    )
    feat = cloud_vlm.extract(ctx)
    assert feat.extraction_method == "skipped:no-page-png"


def test_openai_compatible_successful_extraction(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "openai_api_key": "sk-mock-key",
        "openai_base_url": "https://custom-ai.internal/v1",
        "openai_model": "qwen2.5-vl-72b",
        "config_version": "v1.0",
        "ocr_text": "FAKTURA 2026/01",
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
        assert headers["Authorization"] == "Bearer sk-mock-key"
        resp_payload = {
            "choices": [
                {
                    "message": {
                        "content": "FACTURA 2026/01\nTotal: 121,00 EUR\nNIF: B12345678\nFecha: 15/01/2026",
                    }
                }
            ]
        }
        req = httpx.Request("POST", str(url), headers=headers, json=json)
        return httpx.Response(200, json=resp_payload, request=req)

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = cloud_vlm.extract(ctx)
    assert feat.extraction_method == "cloud_vlm"
    assert "FACTURA 2026/01" in feat.data
    assert feat.page == 0
    assert feat.sha256 == page_sha
    assert feat.extractor_version == cloud_vlm.VERSION
    assert feat.latency_ms >= 0
    assert feat.confidence == 0.95

    # Check request structure
    assert requested_urls == ["https://custom-ai.internal/v1/chat/completions"]
    assert requested_bodies[0]["model"] == "qwen2.5-vl-72b"
    assert requested_bodies[0]["temperature"] == 0.0
    user_content = requested_bodies[0]["messages"][0]["content"]
    assert any(c.get("type") == "image_url" for c in user_content)
    assert any("FAKTURA 2026/01" in c.get("text", "") for c in user_content)

    # Check that cache was populated and next call hits cache
    cached_feat = cloud_vlm.extract(ctx)
    assert cached_feat.extraction_method == "cloud_vlm"
    assert cached_feat.data == feat.data
    # No second HTTP call was made
    assert len(requested_urls) == 1


def test_openai_api_error_returns_skip(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "cloud_api_key": "sk-error-key",
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

    def mock_post_fail(url, headers, json, timeout):
        req = httpx.Request("POST", str(url), headers=headers, json=json)
        return httpx.Response(500, text="Internal Server Error", request=req)

    monkeypatch.setattr(httpx, "post", mock_post_fail)

    feat = cloud_vlm.extract(ctx)
    assert feat.extraction_method.startswith("skipped:cloud-vlm-error:")
    assert feat.extractor_version == cloud_vlm.VERSION
    assert feat.latency_ms >= 0


def test_openai_empty_content_returns_skip(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "cloud_api_key": "sk-empty-key",
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

    def mock_post_empty(url, headers, json, timeout):
        req = httpx.Request("POST", str(url), headers=headers, json=json)
        return httpx.Response(200, json={"choices": [{"message": {"content": "   "}}]}, request=req)

    monkeypatch.setattr(httpx, "post", mock_post_empty)

    feat = cloud_vlm.extract(ctx)
    assert feat.extraction_method == "skipped:cloud-vlm-empty"
    assert feat.extractor_version == cloud_vlm.VERSION
    assert feat.latency_ms >= 0
