"""Parser: features → campos con candidatos (T2)."""

from albertitos.parse.parser import (
    EXTRACTORS,
    FIELD_ORDER,
    TEXT_FEATURE_TYPES,
    field_by_type,
    parse_invoice,
)

__all__ = [
    "EXTRACTORS",
    "FIELD_ORDER",
    "TEXT_FEATURE_TYPES",
    "field_by_type",
    "parse_invoice",
]