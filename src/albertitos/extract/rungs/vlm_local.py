"""Escalón 4: VLM local — PaddleOCR-VL Q8 vía llama-server (OpenAI-compatible, temp 0)."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import httpx

from albertitos.types import ExtractionFeature

from ..cache import FeatureCache

NAME = "vlm"
VERSION = "1"

_DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
_MIN_WORD_CONF = 60.0
_MIN_FIELD_COVERAGE = 0.5
_PROMPT = "OCR:"  # contrato del modelo (docs/decisiones/DECISIONS.md D-001)


def extract(
    pdf_path: Path,
    page_index: int,
    page_image_sha: str | None,
    cache: FeatureCache,
    config: dict[str, Any],
) -> ExtractionFeature:
    if page_image_sha is None:
        return _skip("no-page-image")
    base_url = config.get("llama_base_url", _DEFAULT_BASE_URL)
    try:
        health = httpx.get(f"{base_url}/health", timeout=2.0)
    except httpx.HTTPError:
        return _skip("llama-server-down")
    if health.status_code != 200:
        return _skip("llama-server-down")

    cached = cache.get(page_image_sha, VERSION, config.get("config_version", ""))
    if cached is not None:
        return cached

    # TODO: POST /v1/chat/completions con la imagen (data URL PNG), temp 0,
    # presupuesto de hilos respetado (sidecar fijo — no saturarlo), y doble puerta:
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


def _image_data_url(png_path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(png_path.read_bytes()).decode()


def _skip(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=f"skipped:{reason}", extractor_version=VERSION)
