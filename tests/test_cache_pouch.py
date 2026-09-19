from filemaid.extract.cache import FeatureCache
from filemaid.types import ExtractionFeature


def test_cache_preserves_large_binary_reading_after_reopen(tmp_path):
    cache = FeatureCache(tmp_path / "state")
    data = b"\x00\xff" * 200000
    feature = ExtractionFeature(
        type="page_image", extraction_method="engine", data=data, extractor_version="engine-1"
    )
    cache.put("page", feature, "config")
    restored = FeatureCache(tmp_path / "state").get("page", "engine-1", "config")
    assert restored.data == data
    cache.put(
        "page",
        ExtractionFeature(
            type="page_image", extraction_method="engine", data=b"new", extractor_version="engine-1"
        ),
        "config",
    )
    assert cache.get("page", "engine-1", "config").data == data
