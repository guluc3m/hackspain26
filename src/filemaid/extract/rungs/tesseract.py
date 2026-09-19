"""Escalón 3: Tesseract. Confianza = media ponderada de palabras + cobertura de campos.

SIN IMPLEMENTAR: no escribe caché ni features con data vacía — un stub que
cachease "" envenenaría la clave (page_sha, VERSION, config_version) que
usará la implementación real. Devuelve skipped:stub y la escalera continúa.
"""

from __future__ import annotations

import shutil
import time

from filemaid.types import ExtractionFeature

from .context import PageContext

NAME = "tesseract"
VERSION = "1"


def extract(ctx: PageContext) -> ExtractionFeature:
    t0 = time.monotonic()
    if ctx.page_image_sha is None:
        return _skip("no-page-image", latency_ms=int((time.monotonic() - t0) * 1000))
    if shutil.which("tesseract") is None:
        return _skip("dep:tesseract", latency_ms=int((time.monotonic() - t0) * 1000))

    cached = ctx.cache.get(ctx.page_image_sha, VERSION, ctx.config.get("config_version", ""))
    if cached is not None:
        return cached

    # Doble puerta al implementar el OCR real — lee de config:
    #   rungs.tesseract.min_word_confidence (media ponderada de palabras, 0-100)
    #   rungs.tesseract.min_field_coverage  (fracción de campos esperados)
    # ambas deben pasar para detener la escalera aquí (master/extraction.yaml).
    # Cachear SOLO tras el trabajo real (nunca resultados vacíos de stubs).
    return _skip("stub", latency_ms=int((time.monotonic() - t0) * 1000))


def _skip(reason: str, latency_ms: int = 0) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text",
        extraction_method=f"skipped:{reason}",
        extractor_version=VERSION,
        latency_ms=latency_ms,
    )
