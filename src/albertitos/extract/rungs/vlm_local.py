"""Escalón 4: VLM local — PaddleOCR-VL Q8 vía llama-server (OpenAI-compatible, temp 0).

SIN IMPLEMENTAR la llamada (mismo contrato anti-envenenamiento de caché que
tesseract): prepara el sidecar (arranque bajo demanda, stop por inactividad
— ver albertitos.llama_manager) y si no está disponible degrada.
"""

from __future__ import annotations

from albertitos.types import ExtractionFeature

from .context import PageContext

NAME = "vlm"
VERSION = "1"

_PROMPT = "OCR:"  # contrato del modelo (docs/decisiones/DECISIONS.md D-001)


def extract(ctx: PageContext) -> ExtractionFeature:
    if ctx.page_image_sha is None:
        return _skip("no-page-image")

    cached = ctx.cache.get(ctx.page_image_sha, VERSION, ctx.config.get("config_version", ""))
    if cached is not None:
        return cached

    # Llamada real al implementar: POST {base_url}/v1/chat/completions con la
    # imagen (data URL PNG), _PROMPT, temp 0, doble puerta desde config:
    #   rungs.vlm_local.min_word_confidence / min_field_coverage.
    # El sidecar se obtiene con albertitos.llama_manager.get_manager() —
    # ensure_started() + touch() por petición; stop a los 5 min de inactividad.
    # Cachear SOLO tras el trabajo real.
    return _skip("stub")


def _skip(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=f"skipped:{reason}", extractor_version=VERSION)
