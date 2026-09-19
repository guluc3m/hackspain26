"""Escalón 1: capa de texto con pypdf. Solo se acepta si pasa la plausibilidad."""

from __future__ import annotations

from albertitos.types import ExtractionFeature

from ..plausibility import text_is_plausible
from .context import PageContext

NAME = "pypdf"
VERSION = "1"

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def extract(ctx: PageContext) -> ExtractionFeature:
    if PdfReader is None:
        return _skip(ctx, "dep:pypdf")
    try:
        text = PdfReader(ctx.pdf_path).pages[ctx.page_index].extract_text() or ""
    except Exception as exc:
        return _skip(ctx, f"error:{exc.__class__.__name__}")
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
    )


def _skip(ctx: PageContext, reason: str) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text", extraction_method=f"skipped:{reason}", page=ctx.page_index, extractor_version=VERSION
    )
