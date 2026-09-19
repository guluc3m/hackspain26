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
    mojibake = "ÿþ\x00\uFFFD\uFFFD\uFFFD ()### <<< \x01\x02\x03 ||| ‰‰‰ >>> ((("
    assert not text_is_plausible(mojibake)


def test_texto_vacio_rechazado():
    assert not text_is_plausible("")
    assert not text_is_plausible("   \n\t ")


def test_cache_feature_roundtrip(tmp_path):
    cache = FeatureCache(tmp_path)
    feat = ExtractionFeature(
        type="pdf_text", extraction_method="tesseract", data="hola",
        page=0, sha256=sha256_bytes(b"img"), extractor_version="1",
    )
    cache.put(sha256_bytes(b"img"), feat, "cfg-1")
    got = cache.get(sha256_bytes(b"img"), "1", "cfg-1")
    assert got is not None
    assert got.data == "hola"
    assert cache.get(sha256_bytes(b"img"), "1", "cfg-2") is None
    assert cache.get(sha256_bytes(b"otra"), "1", "cfg-1") is None


def test_ladder_architecture_six_rungs():
    from filemaid.extract.ladder import _RUNGS
    rung_names = [name for name, _, _, _ in _RUNGS]
    assert rung_names == [
        "pypdf",
        "zxing",
        "tesseract",
        "vlm",
        "typesafe_jev",
        "cloud_vlm",
    ]

def test_ladder_execution_fallback_all_rungs(tmp_path):
    from filemaid.extract.ladder import ExtractionLadder
    from filemaid.extract.rungs.context import PageContext
    cache = FeatureCache(tmp_path / "cache")
    ladder = ExtractionLadder(cache=cache, config={}, pages_dir=tmp_path / "pages")

    # Create a valid 1x1 PNG using PIL to exercise extract_page_any (start=1)
    from PIL import Image as PILImage
    import io
    im = PILImage.new("RGB", (10, 10), color="white")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    dummy_img = tmp_path / "page_0.png"
    dummy_img.write_bytes(buf.getvalue())
    extraction = ladder.extract_page_any(dummy_img, 0, start=1)
    assert extraction.page == 0
    methods = [f.extraction_method for f in extraction.features]
    # Should execute through qr -> tesseract -> vlm -> typesafe_jev -> cloud_vlm
    # All skip gracefully without throwing
    assert any("pypdfium2" in m or "skipped" in m for m in methods)
    assert any("typesafe" in m for m in methods)
    assert any("cloud" in m or "api-key" in m for m in methods)
    # Every feature records latency_ms
    for f in extraction.features:
        assert hasattr(f, "latency_ms")
        assert isinstance(f.latency_ms, int)
        assert f.latency_ms >= 0
