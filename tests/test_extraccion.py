from __future__ import annotations

from albertitos.extract.cache import FeatureCache, sha256_bytes
from albertitos.extract.plausibility import text_is_plausible
from albertitos.types import ExtractionFeature


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
