"""Fixtures compartidas de tests."""

from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_path(*parts: str) -> Path:
    return FIXTURES.joinpath(*parts)