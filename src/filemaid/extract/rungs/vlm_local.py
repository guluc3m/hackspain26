"""Escalón 4: VLM local — PaddleOCR-VL Q8 vía llama-server (OpenAI-compatible, temp 0).

El sidecar se gestiona con filemaid.llama_manager: arranque bajo demanda
touch() por petición, stop a los 5 min sin uso. Doble puerta desde config
(master/extraction.yaml, rungs.vlm_local): la confianza de la lectura es la
fracción de campos esperados que el parser encuentra en el texto — si no
llega al umbral, se baja al escalón 5 y el texto NO es contenido.
"""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any

import httpx

from filemaid.store.trace import capture_artifact, capture_response
from filemaid.types import ExtractionFeature

from ..plausibility import text_is_plausible
from ..preprocess import enhance_scan_image
from .context import PageContext, threshold

NAME = "vlm"
VERSION = "vlm-2"

_PROMPT = "OCR:"  # contrato del modelo (docs/decisiones/DECISIONS.md D-001)
_MIN_TEXT_WORDS = 5


def extract(ctx: PageContext) -> ExtractionFeature:
    if ctx.page_image_sha is None:
        return _skip("no-page-image")

    t0 = time.monotonic()
    cached = ctx.cache.get(ctx.page_image_sha, VERSION, ctx.config.get("config_version", ""))
    if cached is not None:
        return cached

    vlm_base_url = (ctx.config.get("vlm_base_url") or "").strip().rstrip("/")
    headers: dict[str, str] = {}
    vlm_model = ctx.config.get("vlm_model") or ""

    if vlm_base_url:
        # Remote or custom endpoint: avoid starting local llama
        endpoint_url = (
            f"{vlm_base_url}/chat/completions"
            if vlm_base_url.endswith("/v1")
            else f"{vlm_base_url}/v1/chat/completions"
        )
        if ctx.config.get("vlm_server_auth"):
            token = ctx.config.get("sync_token") or os.environ.get("FILEMAID_SYNC_TOKEN", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        else:
            custom_key = os.environ.get("FILEMAID_VLM_KEY", "").strip()
            if custom_key:
                headers["Authorization"] = f"Bearer {custom_key}"
    else:
        from filemaid.llama_manager import get_manager

        mgr = get_manager()
        if not mgr.ensure_started():
            return _skip("llama-unavailable", latency_ms=int((time.monotonic() - t0) * 1000))
        mgr.touch()
        endpoint_url = f"{mgr.base_url}/v1/chat/completions"

    # la imagen de página ya existe (el escalón 2 la renderizó/guardó);
    # si no se guardó en disco, re-render no vale la pena: usamos el PNG
    # del pages_dir si está, si no leemos el propio fichero (imágenes sueltas)
    png = _page_png(ctx)
    if png is None:
        return _skip("no-page-png", latency_ms=int((time.monotonic() - t0) * 1000))
    min_conf = threshold(ctx, "vlm_local", "min_field_coverage", 0.5)

    def _query_vlm(img_bytes: bytes) -> str | None:
        r = None
        try:
            payload: dict[str, Any] = {
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(img_bytes).decode()}},
                        {"type": "text", "text": _PROMPT},
                    ],
                }],
                "temperature": 0,
                "max_tokens": 1024,
            }
            if vlm_model:
                payload["model"] = vlm_model
            r = httpx.post(
                endpoint_url,
                headers=headers,
                timeout=120.0,
                json=payload,
            )
            r.raise_for_status()
            response = r.json()
            return response["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError):
            return None
        finally:
            if r is not None:
                capture_response(NAME, r)

    text = _query_vlm(png)
    if text is None:
        return _skip("vlm-error", latency_ms=int((time.monotonic() - t0) * 1000))

    confidence = _field_coverage(text) if (text and text_is_plausible(text) and len(text.split()) >= _MIN_TEXT_WORDS) else 0.0

    # Multi-pass: si la cobertura de campos es baja o falla plausibilidad, reintentar con imagen preprocesada/mejorada
    if confidence < min_conf:
        enhanced_png = enhance_scan_image(png)
        if enhanced_png != png:
            capture_artifact(NAME, "enhanced.png", enhanced_png, "image/png")
            text_retry = _query_vlm(enhanced_png)
            if text_retry and text_is_plausible(text_retry) and len(text_retry.split()) >= _MIN_TEXT_WORDS:
                conf_retry = _field_coverage(text_retry)
                if conf_retry > confidence:
                    text = text_retry
                    confidence = conf_retry

    if not text or not text_is_plausible(text) or len(text.split()) < _MIN_TEXT_WORDS:
        return _skip("vlm-empty", latency_ms=int((time.monotonic() - t0) * 1000))

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
    from filemaid.parse.extractors import all_extractors

    extractors = all_extractors()
    found = sum(1 for _, _, extractor in extractors if extractor(text)[0] is not None)
    return found / len(extractors) if extractors else 0.0


def _skip(reason: str, latency_ms: int = 0) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text",
        extraction_method=f"skipped:{reason}",
        extractor_version=VERSION,
        latency_ms=latency_ms,
    )
