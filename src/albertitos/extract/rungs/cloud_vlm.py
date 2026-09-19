"""Escalón 5: VLM cloud (>25B, multimodal) — vía de escalado.

Su lectura se registra como *otro candidato* (nunca respuesta automática):
la escalera nunca se detiene en este escalón. Cachea igual que el resto
(24/7 ⇒ no re-facturar).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from albertitos.types import ExtractionFeature

from ..cache import FeatureCache

NAME = "cloud_vlm"
VERSION = "1"


def extract(
    pdf_path: Path,
    page_index: int,
    page_image_sha: str | None,
    cache: FeatureCache,
    config: dict[str, Any],
) -> ExtractionFeature:
    if page_image_sha is None:
        return _skip("no-page-image")
    if not config.get("cloud_api_key"):
        return _skip("no-api-key")

    cached = cache.get(page_image_sha, VERSION, config.get("config_version", ""))
    if cached is not None:
        return cached

    # TODO: llamada cloud real (modelo >25B multimodal), registrando
    # engine+version+latencia+hash; resultado como candidato adicional.
    feature = ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME,
        data="",
        page=page_index,
        sha256=page_image_sha,
        extractor_version=VERSION,
    )
    cache.put(page_image_sha, feature, config.get("config_version", ""))
    return feature


def _skip(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=f"skipped:{reason}", extractor_version=VERSION)
