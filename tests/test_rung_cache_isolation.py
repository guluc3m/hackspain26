from __future__ import annotations

from pathlib import Path

import httpx
from PIL import Image

from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.rungs import cloud_vlm, firecrawl, typesafe_jev
from filemaid.extract.rungs.context import PageContext
from filemaid.types import ExtractionFeature


def test_provider_cache_isolates_typed_evidence_text_and_legacy_entries(tmp_path: Path, monkeypatch):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    page_path = pages_dir / "p0.png"
    Image.new("RGB", (8, 8), "white").save(page_path)
    page_sha = sha256_bytes(page_path.read_bytes())
    cache_root = tmp_path / "cache"
    cache = FeatureCache(cache_root)
    config_version = "shared-config"
    firecrawl_url = "https://firecrawl.example/v2/parse"
    cloud_url = "https://cloud.example/v1/chat/completions"
    ctx = PageContext(
        pdf_path=page_path,
        page_index=0,
        cache=cache,
        config={
            "config_version": config_version,
            "rungs": {
                "firecrawl": {
                    "firecrawl_api_key": "test-firecrawl-key",
                    "firecrawl_api_url": firecrawl_url,
                    "timeout": 1.0,
                },
                "cloud_vlm": {
                    "openai_api_key": "test-cloud-key",
                    "openai_base_url": "https://cloud.example/v1",
                    "openai_model": "test-model",
                    "temperature": 0.0,
                    "timeout": 1.0,
                },
            },
        },
        pages_dir=pages_dir,
        page_image_sha=page_sha,
    )
    evidence = ExtractionFeature(
        type="typed_evidence",
        extraction_method="typesafe_jev",
        data={
            "answers": {"is_valid_invoice": {"noul": 0.5}},
            "model": "jev-latest",
            "usage": {"input_tokens": 10, "output_tokens": 1},
        },
        page=0,
        sha256=page_sha,
        extractor_version=typesafe_jev.VERSION,
        confidence=0.5,
    )
    legacy = ExtractionFeature(
        type="pdf_text",
        extraction_method="skipped:low-confidence-0.10",
        data="Stale unqualified provider result",
        page=0,
        sha256=page_sha,
        extractor_version="1",
        confidence=0.1,
    )
    cache.put(page_sha, evidence, config_version)
    cache.put(page_sha, legacy, config_version)

    firecrawl_text = "Factura Firecrawl Cliente Acme Fecha 2026-09-19 Total 121 EUR"
    cloud_text = "Factura Cloud Cliente Acme Fecha 2026-09-19 Total 242 EUR"
    responses = {
        firecrawl_url: {"success": True, "data": {"markdown": firecrawl_text}},
        cloud_url: {"choices": [{"message": {"content": cloud_text}}]},
    }
    requested_urls = []

    def mock_post(url, **kwargs):
        requested_urls.append(url)
        return httpx.Response(200, json=responses[url], request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", mock_post)

    firecrawl_result = firecrawl.extract(ctx)
    cloud_result = cloud_vlm.extract(ctx)
    assert (firecrawl_result.type, firecrawl_result.extraction_method, firecrawl_result.data) == (
        "pdf_text", "firecrawl", firecrawl_text
    )
    assert (cloud_result.type, cloud_result.extraction_method, cloud_result.data) == (
        "pdf_text", "cloud_vlm", cloud_text
    )
    assert requested_urls == [firecrawl_url, cloud_url]

    # Reload from disk and reverse the order: neither engine may see the other's text.
    ctx.cache = FeatureCache(cache_root)
    assert cloud_vlm.extract(ctx) == cloud_result
    assert firecrawl.extract(ctx) == firecrawl_result
    assert requested_urls == [firecrawl_url, cloud_url]
    assert ctx.cache.get(page_sha, typesafe_jev.VERSION, config_version) == evidence
    assert ctx.cache.get(page_sha, "1", config_version) == legacy
