"""Parser: transforma features en campos interpretados (ExtractionField).

Cada campo conserva todos los candidatos (extractor + valor + confianza en
[0,1]). El colapso a escalar ocurre solo cuando una regla lo necesita, y se
registra qué candidato se eligió y por qué (ver architecture.typ §Parser).
"""

from __future__ import annotations

from albertitos.extract.ladder import PageExtraction
from albertitos.types import ExtractionField

from . import extractors

FIELD_TYPES = ("nif", "iban", "total", "iva_amount", "iva_rate", "base", "fecha", "pedido", "proveedor")


def parse_fields(pages: list[PageExtraction]) -> list[ExtractionField]:
    """Ejecuta todos los extractores sobre el contenido de las páginas."""
    fields: dict[str, ExtractionField] = {}

    for page in pages:
        for source in _content_sources(page):
            for field_type, extractor_name, extractor in extractors.all_extractors():
                value, confidence = extractor(source)
                if value is not None and confidence > 0.0:
                    fields.setdefault(field_type, ExtractionField(type=field_type)).add(
                        extractor=extractor_name, value=value, confidence=confidence
                    )

    return list(fields.values())


def _content_sources(page: PageExtraction) -> list[str]:
    """Contenido textual usable por los extractores (features de texto y QR)."""
    sources: list[str] = []
    for feat in page.features:
        if isinstance(feat.data, str) and feat.data and not feat.extraction_method.startswith("skipped"):
            sources.append(feat.data)
    return sources
