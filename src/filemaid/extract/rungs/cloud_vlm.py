"""Escalón 6: VLM cloud (>25B, multimodal) — OpenAI-compatible endpoint.

Configurable para cualquier endpoint compatible con OpenAI (vía config o variables de entorno):
- `OPENAI_BASE_URL` / `openai_base_url` (default: https://api.openai.com/v1)
- `OPENAI_API_KEY` / `openai_api_key` (fallback a cloud_api_key)
- `OPENAI_MODEL` / `openai_model` (default: gpt-4o-mini)
- Temperature: 0.0

Entrada: imagen PNG base64 y/o texto OCR si está disponible.
Salida: ExtractionFeature con el texto/JSON extraído o candidatos.
Métricas: latency_ms y extractor_version.
Caché: (page_image_sha, VERSION, config_version).
Graceful skip si no hay API key configurada o no hay imagen.
"""

from __future__ import annotations

import base64
import io
import os
import time
from typing import Any

import httpx

from filemaid.types import ExtractionFeature

from ..plausibility import text_is_plausible
from .context import PageContext

NAME = "cloud_vlm"
VERSION = "cloud_vlm-1"

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_MODEL = "gpt-4o-mini"
_PROMPT = (
    "Extract all invoice text and key-value fields from this invoice image. "
    "Output the readable text accurately preserving layout, dates, amounts, NIF/CIF, and invoice numbers."
)


def _get_setting(ctx: PageContext, key: str, env_var: str, default: Any = "") -> Any:
    """Obtiene un parámetro de rungs.cloud_vlm, de ctx.config o de variable de entorno."""
    rung_cfg = ctx.config.get("rungs", {}).get(NAME, {})
    if key in rung_cfg and rung_cfg[key] is not None:
        return rung_cfg[key]
    if key in ctx.config and ctx.config[key] is not None:
        return ctx.config[key]
    return os.environ.get(env_var, default)


def extract(ctx: PageContext) -> ExtractionFeature:
    t0 = time.monotonic()

    if ctx.page_image_sha is None:
        return _skip("no-page-image", latency_ms=int((time.monotonic() - t0) * 1000))

    api_key = (
        _get_setting(ctx, "openai_api_key", "OPENAI_API_KEY")
        or _get_setting(ctx, "cloud_api_key", "FILEMAID_CLOUD_API_KEY")
    )
    if not api_key:
        return _skip("no-api-key", latency_ms=int((time.monotonic() - t0) * 1000))

    config_version = ctx.config.get("config_version", "")
    cached = ctx.cache.get(ctx.page_image_sha, VERSION, config_version)
    if cached is not None:
        return cached

    png = _page_png(ctx)
    if png is None:
        return _skip("no-page-png", latency_ms=int((time.monotonic() - t0) * 1000))

    base_url = str(_get_setting(ctx, "openai_base_url", "OPENAI_BASE_URL", _DEFAULT_BASE_URL)).rstrip("/")
    model = str(_get_setting(ctx, "openai_model", "OPENAI_MODEL", _DEFAULT_MODEL))
    temperature = float(_get_setting(ctx, "temperature", "OPENAI_TEMPERATURE", 0.0))
    timeout_sec = float(_get_setting(ctx, "timeout", "OPENAI_TIMEOUT", 60.0))

    # Construir contenido del mensaje de usuario (imagen PNG base64 y/o texto)
    b64_img = base64.b64encode(png).decode("ascii")
    content: list[dict[str, Any]] = [
        {"type": "text", "text": _PROMPT},
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
    ]

    # Si hay texto previo (OCR o capa de texto) en ctx.config o en ctx, se adjunta opcionalmente
    ocr_hint = ctx.config.get("ocr_text")
    if ocr_hint and isinstance(ocr_hint, str):
        content.append({"type": "text", "text": f"Prior OCR text reference:\n{ocr_hint}"})

    req_body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": content,
            }
        ],
        "temperature": temperature,
    }

    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(url, headers=headers, json=req_body, timeout=timeout_sec)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"] or ""
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _skip(f"cloud-vlm-error:{exc.__class__.__name__}", latency_ms=latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)
    if not text or not text.strip():
        return _skip("cloud-vlm-empty", latency_ms=latency_ms)

    confidence = 0.95 if text_is_plausible(text) else 0.5
    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME,
        data=text,
        page=ctx.page_index,
        sha256=ctx.page_image_sha or "",
        extractor_version=VERSION,
        latency_ms=latency_ms,
        confidence=confidence,
    )
    ctx.cache.put(ctx.page_image_sha, feat, config_version)
    return feat


def _page_png(ctx: PageContext) -> bytes | None:
    """PNG de la página: del pages_dir o convirtiendo la ruta si es imagen."""
    if ctx.pages_dir is not None:
        p = ctx.pages_dir / f"p{ctx.page_index}.png"
        if p.is_file():
            return p.read_bytes()
    if ctx.pdf_path.suffix.lower() != ".pdf" and ctx.pdf_path.is_file():
        try:
            from PIL import Image as PILImage

            buf = io.BytesIO()
            PILImage.open(ctx.pdf_path).convert("RGB").save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None
    return None


def _skip(reason: str, latency_ms: int = 0) -> ExtractionFeature:
    return ExtractionFeature(
        type="pdf_text",
        extraction_method=f"skipped:{reason}",
        extractor_version=VERSION,
        latency_ms=latency_ms,
    )
