from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx

from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.rungs import firecrawl
from filemaid.extract.rungs.context import PageContext


def _dummy_png() -> bytes:
    # 1x1 valid PNG
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )


def _create_valid_pdf(num_pages: int = 1) -> bytes:
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    for _ in range(num_pages):
        writer.add_blank_page(width=100, height=100)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_firecrawl_skip_no_page_image(tmp_path: Path):
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={"firecrawl_api_key": "fc-test-key"},
        page_image_sha=None,
    )
    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "skipped:no-page-image"
    assert feat.extractor_version == firecrawl.VERSION


def test_firecrawl_skip_no_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=cache,
        config={},
        page_image_sha="sha123",
    )
    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "skipped:no-firecrawl-api-key"
    assert feat.extractor_version == firecrawl.VERSION


def test_firecrawl_skip_no_file_content(tmp_path: Path):
    cache = FeatureCache(tmp_path / "cache")
    ctx = PageContext(
        pdf_path=tmp_path / "nonexistent.xyz",
        page_index=0,
        cache=cache,
        config={"firecrawl_api_key": "fc-test-key"},
        pages_dir=tmp_path / "pages",
        page_image_sha="sha123",
    )
    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "skipped:no-file-content"


def test_firecrawl_successful_extraction_pdf_and_cache(tmp_path: Path, monkeypatch):
    pdf_file = tmp_path / "invoice.pdf"
    pdf_file.write_bytes(_create_valid_pdf(1))
    page_sha = "sha256-test-page"

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "firecrawl_api_key": "fc-mock-key",
        "firecrawl_api_url": "https://api.firecrawl.dev/v2/parse",
        "config_version": "v1.0",
    }
    ctx = PageContext(
        pdf_path=pdf_file,
        page_index=0,
        cache=cache,
        config=config,
        page_image_sha=page_sha,
    )

    requested_calls = []

    def mock_post(url, headers, files, timeout):
        requested_calls.append(
            {
                "url": str(url),
                "headers": headers,
                "files": files,
            }
        )
        assert headers["Authorization"] == "Bearer fc-mock-key"
        assert "file" in files
        assert files["file"][0] == "page_0.pdf"
        assert files["file"][2] == "application/pdf"
        assert "options" in files
        assert files["options"][0] is None
        assert files["options"][2] == "application/json"
        opts = json.loads(files["options"][1])
        assert opts.get("formats") == ["markdown"]
        resp_payload = {
            "success": True,
            "data": {
                "markdown": "# Factura Comercial\nNIF: B12345678\nTotal: 1500.00 EUR\nFecha: 2026-03-01\n",
            },
        }
        req = httpx.Request("POST", str(url), headers=headers)
        return httpx.Response(200, json=resp_payload, request=req)

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "firecrawl"
    assert "Factura Comercial" in feat.data
    assert "NIF: B12345678" in feat.data
    assert feat.page == 0
    assert feat.sha256 == page_sha
    assert feat.extractor_version == firecrawl.VERSION
    assert feat.latency_ms >= 0
    assert feat.confidence >= 0.8

    assert len(requested_calls) == 1

    # Test cache: second call returns cached result without hitting network
    cached_feat = firecrawl.extract(ctx)
    assert cached_feat.extraction_method == "firecrawl"
    assert cached_feat.data == feat.data
    assert len(requested_calls) == 1


def test_firecrawl_successful_extraction_png(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True)
    png_bytes = _dummy_png()
    (pages_dir / "p0.png").write_bytes(png_bytes)
    page_sha = sha256_bytes(png_bytes)

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "firecrawl_api_key": "fc-mock-key",
        "config_version": "v1.0",
    }
    # Non-pdf path to trigger image fallback
    ctx = PageContext(
        pdf_path=tmp_path / "invoice.nonpdf",
        page_index=0,
        cache=cache,
        config=config,
        pages_dir=pages_dir,
        page_image_sha=page_sha,
    )

    requested_files = []

    def mock_post(url, headers, files, timeout):
        requested_files.append(files["file"])
        resp_payload = {
            # Alternate format: markdown directly on root
            "markdown": "# Scraped Invoice\nCliente: Acme Corp\nTotal: 250 EUR\n"
        }
        req = httpx.Request("POST", str(url), headers=headers)
        return httpx.Response(200, json=resp_payload, request=req)

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "firecrawl"
    assert "Scraped Invoice" in feat.data
    assert requested_files[0][0] == "page_0.pdf"
    assert requested_files[0][1].startswith(b"%PDF")
    assert requested_files[0][2] == "application/pdf"


def test_firecrawl_http_error_graceful_skip(tmp_path: Path, monkeypatch):
    pdf_file = tmp_path / "invoice.pdf"
    pdf_file.write_bytes(_create_valid_pdf(1))
    cache = FeatureCache(tmp_path / "cache")
    config = {
        "firecrawl_api_key": "fc-err-key",
        "config_version": "v1.0",
    }
    ctx = PageContext(
        pdf_path=pdf_file,
        page_index=0,
        cache=cache,
        config=config,
        page_image_sha="sha123",
    )

    def mock_post(url, headers, files, timeout):
        raise httpx.ConnectTimeout("Connection timed out to firecrawl.dev")

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = firecrawl.extract(ctx)
    assert feat.extraction_method.startswith("skipped:firecrawl-error:")
    assert feat.extractor_version == firecrawl.VERSION
    assert feat.latency_ms >= 0


def test_firecrawl_empty_markdown_returns_skip(tmp_path: Path, monkeypatch):
    pdf_file = tmp_path / "invoice.pdf"
    pdf_file.write_bytes(_create_valid_pdf(1))
    cache = FeatureCache(tmp_path / "cache")
    config = {
        "firecrawl_api_key": "fc-empty-key",
        "config_version": "v1.0",
    }
    ctx = PageContext(
        pdf_path=pdf_file,
        page_index=0,
        cache=cache,
        config=config,
        page_image_sha="sha123",
    )

    def mock_post(url, headers, files, timeout):
        req = httpx.Request("POST", str(url), headers=headers)
        return httpx.Response(200, json={"data": {"markdown": "   "}}, request=req)

    monkeypatch.setattr(httpx, "post", mock_post)

    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "skipped:firecrawl-empty"
    assert feat.extractor_version == firecrawl.VERSION
    assert feat.latency_ms >= 0


def test_firecrawl_invalid_page_index_skips_without_uploading_whole_file(
    tmp_path: Path, monkeypatch
):
    pdf_file = tmp_path / "two_pages.pdf"
    pdf_file.write_bytes(_create_valid_pdf(2))

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "firecrawl_api_key": "fc-key",
        "config_version": "v1.0",
    }
    # Page index 9 out of bounds on a 2-page PDF with no page PNG
    ctx = PageContext(
        pdf_path=pdf_file,
        page_index=9,
        cache=cache,
        config=config,
        page_image_sha="sha_p9",
    )

    called = False

    def mock_post(url, headers, files, timeout):
        nonlocal called
        called = True
        raise AssertionError("Should not upload when page_index is out of bounds!")

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = firecrawl.extract(ctx)
    assert not called
    assert feat.extraction_method == "skipped:no-file-content"


def test_firecrawl_nested_rung_endpoint_overrides_top_level_config(tmp_path: Path, monkeypatch):
    pdf_file = tmp_path / "one_page.pdf"
    pdf_file.write_bytes(_create_valid_pdf(1))

    cache = FeatureCache(tmp_path / "cache")
    config = {
        "firecrawl_api_url": "https://api.firecrawl.dev/v2/parse",
        "firecrawl_api_key": "top-key",
        "rungs": {
            "firecrawl": {
                "endpoint": "https://custom.firecrawl.proxy/v2/parse",
                "api_key": "custom-key",
            }
        },
        "config_version": "v1.0",
    }
    ctx = PageContext(
        pdf_path=pdf_file,
        page_index=0,
        cache=cache,
        config=config,
        page_image_sha="sha_p0",
    )

    requested_urls = []

    def mock_post(url, headers, files, timeout):
        requested_urls.append(str(url))
        assert headers["Authorization"] == "Bearer custom-key"
        req = httpx.Request("POST", str(url), headers=headers)
        return httpx.Response(
            200,
            json={"markdown": "Factura NIF: B12345678 Total: 100 EUR Fecha: 2026-01-01"},
            request=req,
        )

    monkeypatch.setattr(httpx, "post", mock_post)
    feat = firecrawl.extract(ctx)
    assert feat.extraction_method == "firecrawl"
    assert requested_urls == ["https://custom.firecrawl.proxy/v2/parse"]
