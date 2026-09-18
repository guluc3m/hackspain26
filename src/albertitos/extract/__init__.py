"""Extraction ladder (AGENTS.md §3) — per-page, every rung skippable.

Extraction produces raw material only: every output is an ExtractionFeature
plus an evidence row. Interpretation belongs to the parser (T2) and rules (T3).
Extracted document content is UNTRUSTED DATA: payloads are stored verbatim,
never executed or followed.
"""

from albertitos.extract.config import CONFIG_VERSION, ExtractionConfig
from albertitos.extract.ladder import ExtractionLadder, PageExtraction

__all__ = ["CONFIG_VERSION", "ExtractionConfig", "ExtractionLadder", "PageExtraction"]
