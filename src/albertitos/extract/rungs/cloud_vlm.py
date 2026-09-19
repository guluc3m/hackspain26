"""Escalón 5: VLM cloud (>25B, multimodal) — vía de escalado.

Su lectura se registra como *otro candidato* (nunca respuesta automática):
la escalera nunca se detiene en este escalón. Cachea igual que el resto
(24/7 ⇒ no re-facturar) — pero solo tras trabajo real, no stubs.
"""

from __future__ import annotations

from albertitos.types import ExtractionFeature

from .context import PageContext

NAME = "cloud_vlm"
VERSION = "1"


def extract(ctx: PageContext) -> ExtractionFeature:
    if ctx.page_image_sha is None:
        return _skip("no-page-image")
    if not ctx.config.get("cloud_api_key"):
        return _skip("no-api-key")

    cached = ctx.cache.get(ctx.page_image_sha, VERSION, ctx.config.get("config_version", ""))
    if cached is not None:
        return cached

    # TODO: llamada cloud real (modelo >25B multimodal), registrando
    # engine+version+latencia+hash; resultado como candidato adicional.
    # Cachear SOLO tras el trabajo real.
    return _skip("stub")


def _skip(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=f"skipped:{reason}", extractor_version=VERSION)
