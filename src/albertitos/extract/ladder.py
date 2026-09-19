"""Escalera de extracción, por página y en orden:

1. Capa de texto (pypdf) — solo si pasa el chequeo de plausibilidad.
2. Rasterizado + QR (pypdfium2 + zxing) — página solo-QR ⇒ el payload es el contenido, parar.
3. Tesseract (OCR) — confianza = media ponderada de palabras + cobertura de campos.
4. VLM local (PaddleOCR-VL Q8 vía llama-server, temp 0) — misma doble puerta.
5. VLM cloud (>25B, multimodal) — vía de escalado; su lectura es otro candidato, nunca respuesta automática.

Cada escalón registra una ExtractionFeature (engine+version+latencia+hash) y es
skippable: dependencia ausente ⇒ `skipped:<reason>` y se sigue; degrada calidad,
nunca para el lote. Escalones 2–5 cachean en (page_sha256, extractor_version,
config_version).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from albertitos.types import ExtractionFeature

from .cache import FeatureCache
from .rungs import cloud_vlm, qr, tesseract, text_layer, vlm_local


@dataclass(slots=True)
class PageExtraction:
    """Resultado de la escalera para una página."""

    page: int
    features: list[ExtractionFeature] = field(default_factory=list)
    content: str = ""  # mejor lectura de contenido disponible (o payload QR)
    stopped_at: str | None = None  # escalón que dio por buena la página


class ExtractionLadder:
    def __init__(
        self,
        cache: FeatureCache,
        config: dict[str, Any],
        pages_dir: Path | None = None,
    ) -> None:
        self.cache = cache
        self.config = config
        self.pages_dir = pages_dir  # imágenes de página para la cola de revisión

    def extract_page(self, pdf_path: Path, page_index: int) -> PageExtraction:
        out = PageExtraction(page=page_index)

        # Escalón 1: capa de texto
        feat = text_layer.extract(pdf_path, page_index)
        out.features.append(feat)
        if feat.extraction_method == "pypdf" and isinstance(feat.data, str):
            out.content = feat.data
            out.stopped_at = feat.extraction_method
            return out

        # Escalón 2: rasterizado + QR
        render = qr.extract(pdf_path, page_index, self.cache, self.config, self.pages_dir)
        out.features.append(render.feature)
        if render.page_image_sha:
            out.content = render.content or out.content
            if render.qr_only:
                out.stopped_at = "zxing"
                return out

        # Escalones 3–5: OCR / VLM local / VLM cloud (cada uno con su puerta de confianza)
        for rung in (tesseract, vlm_local, cloud_vlm):
            feat = rung.extract(pdf_path, page_index, render.page_image_sha, self.cache, self.config)
            out.features.append(feat)
            if feat.extraction_method == rung.NAME and isinstance(feat.data, str) and feat.data:
                out.content = feat.data
                if rung.NAME != cloud_vlm.NAME:  # el cloud nunca es respuesta automática
                    out.stopped_at = rung.NAME
        return out


def extract_document(
    pdf_path: Path,
    cache: FeatureCache,
    config: dict[str, Any],
    pages_dir: Path | None = None,
) -> list[PageExtraction]:
    """Escalera por página (un PDF puede mezclar páginas de distinto tipo)."""
    from pypdf import PdfReader

    ladder = ExtractionLadder(cache, config, pages_dir)
    n_pages = len(PdfReader(pdf_path).pages)
    return [ladder.extract_page(pdf_path, i) for i in range(n_pages)]
