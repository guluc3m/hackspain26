"""Escalón 4: VLM local — PaddleOCR-VL Q8 vía llama-server (OpenAI-compatible, temp 0).

El sidecar se gestiona con albertitos.llama_manager: arranque bajo demanda
touch() por petición, stop a los 5 min sin uso. Doble puerta desde config
(master/extraction.yaml, rungs.vlm_local): la confianza de la lectura es la
fracción de campos esperados que el parser encuentra en el texto — si no
llega al umbral, se baja al escalón 5 y el texto NO es contenido.
"""

from __future__ import annotations

import base64
import io
import time

import httpx

from albertitos.types import ExtractionFeature

from ..plausibility import text_is_plausible
from .context import PageContext, threshold

NAME = "vlm"
VERSION = "1"

_PROMPT = "OCR:"  # contrato del modelo (docs/decisiones/DECISIONS.md D-001)
_MIN_TEXT_WORDS = 5


def extract(ctx: PageContext) -> ExtractionFeature:
    from albertitos.llama_manager import get_manager

    if ctx.page_image_sha is None:
        return _skip("no-page-image")

    cached = ctx.cache.get(ctx.page_image_sha, VERSION, ctx.config.get("config_version", ""))
    if cached is not None:
        return cached

    mgr = get_manager()
    if not mgr.ensure_started():
        return _skip("llama-unavailable")
    mgr.touch()

    # la imagen de página ya existe (el escalón 2 la renderizó/guardó);
    # si no se guardó en disco, re-render no vale la pena: usamos el PNG
    # del pages_dir si está, si no leemos el propio fichero (imágenes sueltas)
    png = _page_png(ctx)
    if png is None:
        return _skip("no-page-png")

    t0 = time.monotonic()
    try:
        r = httpx.post(
            f"{mgr.base_url}/v1/chat/completions",
            timeout=120.0,
            json={
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}},
                        {"type": "text", "text": _PROMPT},
                    ],
                }],
                "temperature": 0,
            },
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError):
        return _skip("vlm-error")

    if not text or not text_is_plausible(text) or len(text.split()) < _MIN_TEXT_WORDS:
        return _skip("vlm-empty")

    confidence = _field_coverage(text)
    min_conf = threshold(ctx, "vlm_local", "min_field_coverage", 0.5)
    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME if confidence >= min_conf else f"skipped:low-confidence-{confidence:.2f}",
        data=text,
        page=ctx.page_index,
        sha256=ctx.page_image_sha or "",
        extractor_version=VERSION,
        latency_ms=int((time.monotonic() - t0) * 1000),
        confidence=confidence,
    )
    ctx.cache.put(ctx.page_image_sha, feat, ctx.config.get("config_version", ""))
    return feat


def _page_png(ctx: PageContext) -> bytes | None:
    """PNG de la página: del pages_dir (lo dejó el escalón 2) o del fichero suelto."""
    if ctx.pages_dir is not None:
        p = ctx.pages_dir / f"p{ctx.page_index}.png"
        if p.is_file():
            return p.read_bytes()
    if ctx.pdf_path.suffix.lower() != ".pdf":
        try:
            from PIL import Image as PILImage

            buf = io.BytesIO()
            PILImage.open(ctx.pdf_path).convert("RGB").save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None
    return None


def _field_coverage(text: str) -> float:
    """Fracción de tipos de campo que algún extractor encuentra en el texto."""
    # import perezoso: parse importa extract.ladder (PageExtraction) — ciclo
    from albertitos.parse.extractors import all_extractors

    extractors = all_extractors()
    found = sum(1 for _, _, extractor in extractors if extractor(text)[0] is not None)
    return found / len(extractors) if extractors else 0.0


def _skip(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="pdf_text", extraction_method=f"skipped:{reason}", extractor_version=VERSION)
