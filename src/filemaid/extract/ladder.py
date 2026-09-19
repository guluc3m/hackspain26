"""Escalera de extracción, por página y en orden (PDF), o de una pieza (imágenes):

1. Capa de texto (pypdf) — solo si pasa el chequeo de plausibilidad.
2. Rasterizado + QR (pypdfium2 + zxing) — página solo-QR ⇒ el payload es el contenido, parar.
3. Tesseract (OCR) — confianza = media ponderada de palabras + cobertura de campos.
4. VLM local (PaddleOCR-VL Q8 vía llama-server, temp 0) — misma doble puerta.
5. TypeSafe System One Jev — juicios tipados sobre texto previo, nunca OCR ni parada.
6. Firecrawl — parser documental de respaldo.
7. VLM cloud (>25B, multimodal / OpenAI-compatible endpoint) — vía de escalado; su lectura es otro candidato, nunca respuesta automática.
Cada escalón registra ExtractionFeatures (engine+version+latencia+hash) y es
skippable: dependencia ausente ⇒ `skipped:<reason>` y se sigue; degrada calidad,
nunca para el lote. Escalones 2–7 cachean en (page_sha256, extractor_version,
config_version).

La interfaz es uniforme: cada escalón es `extract(PageContext) -> RungResult`
y decide por sí mismo si puede detener la escalera (`auto_stop`). Añadir un
escalón = añadirlo a _RUNGS; tocar el bucle jamás.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from filemaid.store.trace import current_trace
from filemaid.types import ExtractionFeature

from .cache import FeatureCache
from .rungs import cloud_vlm, firecrawl, qr, tesseract, text_layer, typesafe_jev, vlm_local
from .rungs.context import PageContext


@dataclass(slots=True)
class PageExtraction:
    """Resultado de la escalera para una página."""

    page: int
    features: list[ExtractionFeature] = field(default_factory=list)
    content: str = ""  # mejor lectura de contenido disponible (o payload QR)
    stopped_at: str | None = None  # escalón que dio por buena la página


@dataclass(slots=True)
class RungResult:
    """Salida uniforme de un escalón: features, contenido y si la página está resuelta."""

    features: list[ExtractionFeature] = field(default_factory=list)
    content: str = ""
    resolved: bool = False  # True ⇒ la escalera para aquí (stopped_at = NAME del escalón)


def _wrap_text(feat: ExtractionFeature) -> RungResult:
    """Adaptador para escalones que devuelven una feature simple."""
    data = feat.data if isinstance(feat.data, str) else ""
    ok = not feat.extraction_method.startswith("skipped") and bool(data)
    return RungResult([feat], content=data, resolved=ok)


def _wrap_evidence(feat: ExtractionFeature) -> RungResult:
    """Los juicios tipados no son texto de factura ni resuelven la página."""
    return RungResult([feat])


_RUNGS: list[tuple[str, Callable[[PageContext], Any], bool, Callable[[ExtractionFeature], RungResult] | None]] = [
    # (name, módulo.extract, auto_stop, adaptador opcional)
    (text_layer.NAME, text_layer.extract, True, _wrap_text),
    (qr.NAME, qr.extract, True, None),  # QrRungResult ya trae resolved implícito vía qr_only
    (tesseract.NAME, tesseract.extract, True, _wrap_text),
    (vlm_local.NAME, vlm_local.extract, True, _wrap_text),
    (typesafe_jev.NAME, typesafe_jev.extract, False, _wrap_evidence),
    (firecrawl.NAME, firecrawl.extract, True, _wrap_text),
    (cloud_vlm.NAME, cloud_vlm.extract, False, _wrap_text),  # el cloud nunca es respuesta automática
]


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

    def extract_page_any(self, path: Path, page_index: int, start: int = 1) -> PageExtraction:
        """Ejecuta la escalera desde el escalón `start` (0-index).

        Una imagen (png/jpg/...) entra directo en el escalón 2: no hay capa
        de texto que comprobar; el rasterizado es la propia imagen.
        """
        out = PageExtraction(page=page_index)
        ctx = PageContext(
            pdf_path=path,
            page_index=page_index,
            cache=self.cache,
            config=self.config,
            pages_dir=self.pages_dir,
        )
        for name, rung_extract, auto_stop, adapter in _RUNGS[start:]:
            result = rung_extract(ctx)
            if isinstance(result, RungResult):
                rr = result
            elif isinstance(result, qr.QrRungResult):
                if result.page_image_sha and not ctx.page_image_sha:
                    ctx.page_image_sha = result.page_image_sha
                # el payload ES el contenido (dato no confiado, nunca instrucciones)
                rr = RungResult(result.features, content=result.content, resolved=result.qr_only)
            else:
                rr = adapter(result) if adapter else RungResult([result])
            if trace := current_trace():
                trace.rung(page_index, name, rr.features, self.pages_dir)

            out.features.extend(rr.features)
            if rr.content:
                out.content = rr.content
                ctx.ocr_text = rr.content
            if rr.resolved and auto_stop:
                out.stopped_at = name
                if trace := current_trace():
                    trace.page(out)
                return out
        if trace := current_trace():
            trace.page(out)
        return out

    def extract_page(self, pdf_path: Path, page_index: int) -> PageExtraction:
        return self.extract_page_any(pdf_path, page_index, start=0)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def extract_document(
    pdf_path: Path,
    cache: FeatureCache,
    config: dict[str, Any],
    pages_dir: Path | None = None,
) -> list[PageExtraction]:
    """Escalera por página (un PDF puede mezclar páginas de distinto tipo)."""
    return extract_file(pdf_path, cache, config, pages_dir)


def extract_file(
    path: Path,
    cache: FeatureCache,
    config: dict[str, Any],
    pages_dir: Path | None = None,
) -> list[PageExtraction]:
    """Escalera sobre un fichero: PDF por página, imagen de una pieza.

    El tipo de fichero se decide AQUÍ; los escalones y el motor de reglas
    no saben nada de formatos (architecture.typ §4).
    """
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return [ExtractionLadder(cache, config, pages_dir).extract_page_any(path, 0, start=1)]
    if suffix != ".pdf":
        raise ValueError(f"formato no soportado: {suffix}")
    from pypdf import PdfReader

    ladder = ExtractionLadder(cache, config, pages_dir)
    return [ladder.extract_page(path, i) for i in range(len(PdfReader(path).pages))]
