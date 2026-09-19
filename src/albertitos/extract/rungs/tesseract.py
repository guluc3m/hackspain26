"""Escalón 3: Tesseract. Confianza = media ponderada de palabras + cobertura de campos."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from albertitos.types import ExtractionFeature

from ..cache import FeatureCache

NAME = "tesseract"
VERSION = "1"

_MIN_WORD_CONF = 60.0
_MIN_FIELD_COVERAGE = 0.5


def extract(
    pdf_path: Path,
    page_index: int,
    page_image_sha: str | None,
    cache: FeatureCache,
    config: dict[str, Any],
) -> ExtractionFeature:
    if page_image_sha is None:
        return _skip("no-page-image")
    if shutil.which("tesseract") is None:
        return _skip("dep:tesseract")

    cached = cache.get(page_image_sha, VERSION, config.get("config_version", ""))
    if cached is not None:
        return cached

    # TODO: OCR real (psm configurable, tessdata user-space) + doble puerta:
    #   conf_palabras >= _MIN_WORD_CONF  y  cobertura_campos >= _MIN_FIELD_COVERAGE.
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
