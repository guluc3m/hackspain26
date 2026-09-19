"""Escalón 1: capa de texto con pypdf. Solo se acepta si pasa la plausibilidad."""

from __future__ import annotations

import time

from filemaid.types import ExtractionFeature

from ..plausibility import text_is_plausible
from .context import PageContext

NAME = "pypdf"
VERSION = "pypdf-1"

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def extract(ctx: PageContext) -> ExtractionFeature:
    t0 = time.monotonic()
    if PdfReader is None:
        return _skip(ctx, "dep:pypdf", latency_ms=int((time.monotonic() - t0) * 1000))
    try:
        text = PdfReader(ctx.pdf_path).pages[ctx.page_index].extract_text() or ""
    except Exception as exc:
        return _skip(ctx, f"error:{exc.__class__.__name__}", latency_ms=int((time.monotonic() - t0) * 1000))
    ok = text_is_plausible(
        text,
        ctx.config.get("rungs", {}).get("text_layer", {}).get("plausibility"),
    )
    return ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME if ok else "skipped:implausible-text",
        data=text,
        page=ctx.page_index,
        extractor_version=VERSION,
        confidence=1.0 if ok else 0.0,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


def _skip(ctx: PageContext, reason: str, latency_ms: int = 0) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text",
        extraction_method=f"skipped:{reason}",
        page=ctx.page_index,
        extractor_version=VERSION,
        latency_ms=latency_ms,
    )
