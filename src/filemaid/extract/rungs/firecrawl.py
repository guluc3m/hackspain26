"""Escalón Firecrawl: parser de documentos vía HTTP POST https://api.firecrawl.dev/v2/parse.

Envía el documento como PDF de 1 página (aislado por página) mediante multipart/form-data:
  file=@page_N.pdf;type=application/pdf
  options={"formats": ["markdown"]};type=application/json
Extrae el contenido markdown retornado (`r.json().get("data", {}).get("markdown")` o `r.json().get("markdown")`).
Retorna ExtractionFeature(type="pdf_text", extraction_method=NAME, data=markdown_text, latency_ms=..., confidence=...).
Cachea sobre (page_image_sha, VERSION, config_version).
Skips limpiamente si no hay API key configurada (_skip("no-firecrawl-api-key")).
"""

from __future__ import annotations

import io
import json
import os
import time
from typing import Any

import httpx

from filemaid.types import ExtractionFeature

from ..plausibility import text_is_plausible
from .context import PageContext, threshold

NAME = "firecrawl"
VERSION = "firecrawl-2"

_DEFAULT_API_URL = "https://api.firecrawl.dev/v2/parse"


def _get_setting(
    ctx: PageContext,
    keys: str | list[str],
    env_vars: str | list[str],
    default: Any = "",
) -> Any:
    """Obtiene un parámetro de rungs.firecrawl, de ctx.config o de variable de entorno.
    Comprueba todas las claves en rungs.firecrawl primero, luego en ctx.config, luego en env."""
    key_list = [keys] if isinstance(keys, str) else keys
    env_list = [env_vars] if isinstance(env_vars, str) else env_vars

    rung_cfg = ctx.config.get("rungs", {}).get(NAME, {})
    for k in key_list:
        if k in rung_cfg and rung_cfg[k] is not None and rung_cfg[k] != "":
            return rung_cfg[k]
    for k in key_list:
        if k in ctx.config and ctx.config[k] is not None and ctx.config[k] != "":
            return ctx.config[k]
    for ev in env_list:
        val = os.environ.get(ev)
        if val is not None and val != "":
            return val
    return default


def extract(ctx: PageContext) -> ExtractionFeature:
    t0 = time.monotonic()

    if ctx.page_image_sha is None:
        return _skip("no-page-image", latency_ms=int((time.monotonic() - t0) * 1000))

    api_key = _get_setting(
        ctx,
        ["firecrawl_api_key", "api_key"],
        ["FIRECRAWL_API_KEY"],
    )
    if not api_key:
        return _skip("no-firecrawl-api-key", latency_ms=int((time.monotonic() - t0) * 1000))

    config_version = ctx.config.get("config_version", "")
    cached = ctx.cache.get(ctx.page_image_sha, VERSION, config_version)
    if cached is not None:
        return cached

    api_url = str(
        _get_setting(
            ctx,
            ["endpoint", "firecrawl_api_url", "api_url"],
            ["FIRECRAWL_API_URL"],
            _DEFAULT_API_URL,
        )
    ).rstrip("/")
    timeout_sec = float(_get_setting(ctx, "timeout", "FIRECRAWL_TIMEOUT", 60.0))

    # /v2/parse admite PDF. Para aislar por página y evitar sangrado multi-página:
    # Extraer únicamente la página específica como PDF de 1 página (vía pypdf)
    # o si es imagen/PNG, convertirla a un PDF de 1 página en memoria vía PIL.
    pdf_bytes: bytes | None = None
    if ctx.pdf_path.suffix.lower() == ".pdf" and ctx.pdf_path.is_file():
        try:
            from pypdf import PdfReader, PdfWriter

            reader = PdfReader(ctx.pdf_path)
            if 0 <= ctx.page_index < len(reader.pages):
                writer = PdfWriter()
                writer.add_page(reader.pages[ctx.page_index])
                buf = io.BytesIO()
                writer.write(buf)
                pdf_bytes = buf.getvalue()
        except Exception:
            pdf_bytes = None

    if pdf_bytes is None:
        png = _page_png(ctx)
        if png is not None:
            try:
                from PIL import Image as PILImage

                img = PILImage.open(io.BytesIO(png)).convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="PDF")
                pdf_bytes = buf.getvalue()
            except Exception:
                pdf_bytes = None

    if pdf_bytes is None:
        return _skip("no-file-content", latency_ms=int((time.monotonic() - t0) * 1000))

    headers = {
        "Authorization": f"Bearer {api_key}",
    }

    # multipart/form-data con archivo PDF y opciones codificadas como application/json
    files = {
        "file": (f"page_{ctx.page_index}.pdf", pdf_bytes, "application/pdf"),
        "options": (None, json.dumps({"formats": ["markdown"]}), "application/json"),
    }

    try:
        resp = httpx.post(
            api_url,
            headers=headers,
            files=files,
            timeout=timeout_sec,
        )
        resp.raise_for_status()
        res_json = resp.json()
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _skip(f"firecrawl-error:{exc.__class__.__name__}", latency_ms=latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Extraer markdown content: r.json().get("data", {}).get("markdown") o r.json().get("markdown")
    markdown_text = ""
    if isinstance(res_json, dict):
        data_field = res_json.get("data")
        if isinstance(data_field, dict):
            markdown_text = data_field.get("markdown") or ""
        if not markdown_text:
            markdown_text = res_json.get("markdown") or ""

    if not isinstance(markdown_text, str) or not markdown_text.strip():
        return _skip("firecrawl-empty", latency_ms=latency_ms)

    markdown_text = markdown_text.strip()
    confidence = 0.90 if text_is_plausible(markdown_text) else 0.50
    min_confidence = threshold(ctx, NAME, "min_confidence", 0.6)

    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME
        if confidence >= min_confidence
        else f"skipped:low-confidence-{confidence:.2f}",
        data=markdown_text,
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
