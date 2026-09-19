"""Escalón 1: capa de texto con pypdf. Solo se acepta si pasa la plausibilidad."""

from __future__ import annotations

from pathlib import Path

from albertitos.types import ExtractionFeature

from ..plausibility import text_is_plausible

NAME = "pypdf"
VERSION = "1"

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None


def extract(pdf_path: Path, page_index: int) -> ExtractionFeature:
    if PdfReader is None:
        return _skipped("dep:pypdf")
    try:
        text = PdfReader(pdf_path).pages[page_index].extract_text() or ""
    except Exception as exc:
        return _skipped(f"error:{exc.__class__.__name__}")
    ok = text_is_plausible(text)
    return ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME if ok else "skipped:implausible-text",
        data=text,
        page=page_index,
        extractor_version=VERSION,
        confidence=1.0 if ok else 0.0,
    )


def _skipped(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=f"skipped:{reason}", page=0, extractor_version=VERSION)
