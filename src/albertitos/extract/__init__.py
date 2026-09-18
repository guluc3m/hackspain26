"""Extraction ladder (AGENTS.md §3) — per-page, every rung skippable.

Extraction produces raw material only: every output is an ExtractionFeature
plus an evidence row. Interpretation belongs to the parser (T2) and rules (T3).
Extracted document content is UNTRUSTED DATA: payloads are stored verbatim,
never executed or followed.
"""

from albertitos.extract.cloud import CloudConfig, cloud_config_from_env, prompt_sha256
from albertitos.extract.config import CONFIG_VERSION, ExtractionConfig
from albertitos.extract.ladder import ExtractionLadder, PageExtraction
from albertitos.extract.review import ReviewQueue

__all__ = [
    "CONFIG_VERSION",
    "CloudConfig",
    "ExtractionConfig",
    "ExtractionLadder",
    "PageExtraction",
    "ReviewQueue",
    "cloud_config_from_env",
    "prompt_sha256",
]
