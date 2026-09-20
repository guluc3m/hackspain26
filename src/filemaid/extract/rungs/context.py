"""Contexto de página compartido por todos los escalones de la escalera.

Un solo objeto pasa por cada escalón: nada de firmas divergentes
(`extract(pdf, page, config)` vs `extract(pdf, page, sha, cache, config)`).
Añadir un escalón nuevo no toca la escalera (architecture.typ §4).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..cache import FeatureCache


@dataclass(slots=True)
class PageContext:
    """Entrada uniforme de un escalón: PDF, página, caché y config."""

    pdf_path: Path
    page_index: int
    cache: FeatureCache
    config: dict[str, Any]
    pages_dir: Path | None = None  # imágenes de página para la cola de revisión
    page_image_sha: str | None = None  # lo fija el escalón rasterizador (2)
    ocr_text: str = ""  # última lectura textual de esta página, incluso con baja confianza


def threshold(ctx: PageContext, rung: str, key: str, default: float) -> float:
    """Lee rungs.<rung>.<key> de master/extraction.yaml con default."""
    return float(ctx.config.get("rungs", {}).get(rung, {}).get(key, default))


def remote_allowed(ctx: PageContext) -> bool:
    """Standalone sets remote_rungs_enabled=False: no rung may contact anything."""
    return bool(ctx.config.get("remote_rungs_enabled", True))
