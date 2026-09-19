from __future__ import annotations

from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.plausibility import text_is_plausible
from filemaid.types import ExtractionFeature


def test_texto_bueno_pasa():
    texto = (
        "FACTURA 2026/001 Fecha: 15/01/2026 Total: 121,00 EUR "
        "Base imponible: 100,00 EUR IVA: 21,00 EUR Proveedor S.L. NIF B12345678"
    )
    assert text_is_plausible(texto)


def test_mojibake_cid_rechazado():
    mojibake = "ÿþ\x00\ufffd\ufffd\ufffd ()### <<< \x01\x02\x03 ||| ‰‰‰ >>> ((("
    assert not text_is_plausible(mojibake)


def test_texto_vacio_rechazado():
    assert not text_is_plausible("")
    assert not text_is_plausible("   \n\t ")


def test_cache_feature_roundtrip(tmp_path):
    cache = FeatureCache(tmp_path)
    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method="tesseract",
        data="hola",
        page=0,
        sha256=sha256_bytes(b"img"),
        extractor_version="1",
    )
    cache.put(sha256_bytes(b"img"), feat, "cfg-1")
    got = cache.get(sha256_bytes(b"img"), "1", "cfg-1")
    assert got is not None
    assert got.data == "hola"
    assert cache.get(sha256_bytes(b"img"), "1", "cfg-2") is None
    assert cache.get(sha256_bytes(b"otra"), "1", "cfg-1") is None


def test_ladder_architecture_seven_rungs():
    from filemaid.extract.ladder import _RUNGS

    rung_names = [name for name, _, _, _ in _RUNGS]
    assert rung_names == [
        "pypdf",
        "zxing",
        "tesseract",
        "vlm",
        "typesafe_jev",
        "firecrawl",
        "cloud_vlm",
    ]


def test_ladder_execution_fallback_all_rungs(tmp_path):
    from filemaid.extract.ladder import ExtractionLadder

    cache = FeatureCache(tmp_path / "cache")
    ladder = ExtractionLadder(cache=cache, config={}, pages_dir=tmp_path / "pages")

    # Create a valid 1x1 PNG using PIL to exercise extract_page_any (start=1)
    import io

    from PIL import Image as PILImage

    im = PILImage.new("RGB", (10, 10), color="white")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    dummy_img = tmp_path / "page_0.png"
    dummy_img.write_bytes(buf.getvalue())
    extraction = ladder.extract_page_any(dummy_img, 0, start=1)
    assert extraction.page == 0
    methods = [f.extraction_method for f in extraction.features]
    # Should execute through qr -> tesseract -> vlm -> typesafe_jev -> firecrawl -> cloud_vlm
    # All skip gracefully without throwing
    assert any("pypdfium2" in m or "skipped" in m for m in methods)
    assert any("typesafe" in m for m in methods)
    assert any("firecrawl" in m for m in methods)
    assert any("cloud" in m or "api-key" in m for m in methods)
    # Every feature records latency_ms
    for f in extraction.features:
        assert hasattr(f, "latency_ms")
        assert isinstance(f.latency_ms, int)
        assert f.latency_ms >= 0


def test_typesafe_evidence_cannot_stop_firecrawl_or_supply_invoice_fields(tmp_path, monkeypatch):
    import httpx

    from filemaid.extract import ladder as ladder_module
    from filemaid.extract.ladder import ExtractionLadder, PageExtraction
    from filemaid.extract.rungs import typesafe_jev
    from filemaid.parse.parser import parse_fields

    prior_text = "Documento parcialmente legible"
    fallback_text = "FACTURA. Total: 121,00 EUR. Fecha: 15/01/2026."
    requested_states = []
    fallback_hints = []
    response = {
        "model": "jev-latest",
        "usage": {"input_tokens": 10, "output_tokens": 4},
        "answers": {
            "is_invoice": {"type": "noul", "noul": 1.0},
            "has_fiscal_data": {"type": "noul", "noul": 1.0},
            "document_quality": {
                "type": "score",
                "score": 2,
                "confidence": 1.0,
                "legend": {"0": "Ilegible", "1": "Parcial", "2": "Legible"},
                "probabilities": {"0": 0.0, "1": 0.0, "2": 1.0},
            },
            "document_category": {
                "type": "choice",
                "choice": "invoice",
                "confidence": 1.0,
                "probabilities": {"invoice": 1.0, "receipt": 0.0, "other": 0.0},
            },
        },
        "provider_note": "TOTAL: 9999,00 EUR. NIF: B12345678.",
    }

    def mock_post(url, **kwargs):
        requested_states.append(kwargs["json"]["state"])
        return httpx.Response(200, json=response, request=httpx.Request("POST", url))

    def prior_reading(ctx):
        ctx.page_image_sha = f"sha-{ctx.page_index}"
        return ExtractionFeature(
            type="pdf_text",
            extraction_method="skipped:low-confidence-0.20",
            data=prior_text if ctx.page_index == 0 else "",
            confidence=0.2,
        )

    def skipped(ctx):
        return ExtractionFeature(type="pdf_text", extraction_method="skipped:unavailable")

    def firecrawl(ctx):
        fallback_hints.append(ctx.ocr_text)
        return ExtractionFeature(type="pdf_text", extraction_method="firecrawl", data=fallback_text)

    # Preserve the real TypeSafe function, stop policy and adapter from the registry.
    rungs = []
    for name, extract, auto_stop, adapter in ladder_module._RUNGS:
        if name == "tesseract":
            extract = prior_reading
        elif name == "firecrawl":
            extract = firecrawl
        elif name != typesafe_jev.NAME:
            extract = skipped
        rungs.append((name, extract, auto_stop, adapter))
    monkeypatch.setattr(ladder_module, "_RUNGS", rungs)
    monkeypatch.setattr(httpx, "post", mock_post)
    config = {"typesafe_api_key": "test-key", "ocr_text": "Must not leak into either page"}
    ladder = ExtractionLadder(FeatureCache(tmp_path / "cache"), config)
    first = ladder.extract_page(tmp_path / "doc.pdf", 0)
    second = ladder.extract_page(tmp_path / "doc.pdf", 1)

    assert requested_states == [{"ocr_text": prior_text, "page_index": 0}]
    assert fallback_hints == [prior_text, ""]
    assert config["ocr_text"] == "Must not leak into either page"
    assert first.stopped_at == second.stopped_at == "firecrawl"
    assert first.content == second.content == fallback_text
    evidence = next(feat for feat in first.features if feat.type == "typed_evidence")
    assert evidence.confidence == 1.0
    assert parse_fields([PageExtraction(page=0, features=[evidence])]) == []
    fallback = next(feat for feat in first.features if feat.extraction_method == "firecrawl")
    actual_fields = [(field.type, field.values) for field in parse_fields([first])]
    fallback_fields = [
        (field.type, field.values)
        for field in parse_fields([PageExtraction(page=0, features=[fallback])])
    ]
    assert actual_fields == fallback_fields
    assert any(feat.extraction_method == "skipped:typesafe-no-ocr-text" for feat in second.features)


def test_typesafe_evidence_preserves_prior_page_content_when_fallbacks_skip(tmp_path, monkeypatch):
    from filemaid.extract import ladder as ladder_module
    from filemaid.extract.ladder import ExtractionLadder

    prior_text = "Texto OCR parcial"

    def evidence(ctx):
        return ExtractionFeature(
            type="typed_evidence",
            extraction_method="typesafe_jev",
            data={"answers": {"is_invoice": {"type": "noul", "noul": 1.0}}},
            confidence=1.0,
        )

    def prior(ctx):
        return ExtractionFeature(
            type="pdf_text", extraction_method="skipped:low-confidence", data=prior_text
        )

    def skipped(ctx):
        return ExtractionFeature(type="pdf_text", extraction_method="skipped:unavailable")

    rungs = [
        (
            name,
            evidence if name == "typesafe_jev" else prior if name == "tesseract" else skipped,
            auto_stop,
            adapter,
        )
        for name, _, auto_stop, adapter in ladder_module._RUNGS
    ]
    monkeypatch.setattr(ladder_module, "_RUNGS", rungs)
    page = ExtractionLadder(FeatureCache(tmp_path / "cache"), {}).extract_page(
        tmp_path / "doc.pdf", 0
    )
    assert page.content == prior_text
    assert page.stopped_at is None
