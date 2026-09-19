"""Escalón 5: TypeSafe System One model ("jev-latest") vía HTTP POST https://api.typesafe.ai/v1/systemone.

Evalúa preguntas tipadas contra el contenido de página o estado de imagen base64.
Preguntas para campos: validez documental de factura (nif, iban, total, fecha, pedido, iva).
Cachea sobre (page_image_sha, VERSION, config_version).
Mide latencia (latency_ms).
Fallback graceful con _skip("no-typesafe-api-key") si falta API key o error.
"""

from __future__ import annotations

import base64
import io
import json
import math
import os
import time
from typing import Any

import httpx

from filemaid.types import ExtractionFeature

from ..plausibility import text_is_plausible
from .context import PageContext, threshold

NAME = "typesafe_jev"
VERSION = "1"

_DEFAULT_API_URL = "https://api.typesafe.ai/v1/systemone"
_DEFAULT_MODEL = "jev-latest"

# Preguntas tipadas para evaluar sobre la factura
SYSTEMONE_QUESTIONS: dict[str, dict[str, Any]] = {
    "is_valid_invoice": {
        "type": "bool",
        "instructions": "¿Es este documento una factura válida o justificante de gasto comercial?",
    },
    "nif": {
        "type": "text",
        "instructions": "Número de identificación fiscal (NIF/CIF/NIE) del emisor o proveedor.",
    },
    "iban": {
        "type": "text",
        "instructions": "Código IBAN de la cuenta bancaria para pago si aparece.",
    },
    "total": {
        "type": "text",
        "instructions": "Importe total a pagar de la factura con moneda o decimales.",
    },
    "fecha": {
        "type": "text",
        "instructions": "Fecha de expedición o emisión de la factura.",
    },
    "pedido": {
        "type": "text",
        "instructions": "Número o código de pedido / orden de compra asociado si existe.",
    },
    "iva": {
        "type": "text",
        "instructions": "Cuota o porcentaje de IVA desglosado en la factura.",
    },
}


def _get_setting(ctx: PageContext, key: str, env_var: str, default: Any = "") -> Any:
    """Obtiene un parámetro de rungs.typesafe_jev, de ctx.config o de variable de entorno."""
    rung_cfg = ctx.config.get("rungs", {}).get(NAME, {})
    if key in rung_cfg and rung_cfg[key] is not None and rung_cfg[key] != "":
        return rung_cfg[key]
    if key in ctx.config and ctx.config[key] is not None and ctx.config[key] != "":
        return ctx.config[key]
    return os.environ.get(env_var, default)


def extract(ctx: PageContext) -> ExtractionFeature:
    t0 = time.monotonic()

    if ctx.page_image_sha is None:
        return _skip("no-page-image", latency_ms=int((time.monotonic() - t0) * 1000))

    api_key = (
        _get_setting(ctx, "typesafe_api_key", "TYPESAFE_API_KEY")
        or _get_setting(ctx, "api_key", "TYPESAFE_API_KEY")
    )
    if not api_key:
        return _skip("no-typesafe-api-key", latency_ms=int((time.monotonic() - t0) * 1000))

    config_version = ctx.config.get("config_version", "")
    cached = ctx.cache.get(ctx.page_image_sha, VERSION, config_version)
    if cached is not None:
        return cached

    png = _page_png(ctx)
    if png is None:
        return _skip("no-page-png", latency_ms=int((time.monotonic() - t0) * 1000))

    api_url = str(
        _get_setting(ctx, "typesafe_api_url", "TYPESAFE_API_URL")
        or _get_setting(ctx, "endpoint", "TYPESAFE_API_URL", _DEFAULT_API_URL)
    ).rstrip("/")
    model = str(
        _get_setting(ctx, "typesafe_model", "TYPESAFE_MODEL")
        or _get_setting(ctx, "model", "TYPESAFE_MODEL", _DEFAULT_MODEL)
    )
    timeout_sec = float(_get_setting(ctx, "timeout", "TYPESAFE_TIMEOUT", 60.0))

    b64_img = base64.b64encode(png).decode("ascii")

    # Si hay texto previo (OCR o capa de texto), puede incluirse en el state
    ocr_hint = ctx.config.get("ocr_text", "")
    state: dict[str, Any] = {
        "image": f"data:image/png;base64,{b64_img}",
        "page_index": ctx.page_index,
    }
    if ocr_hint:
        state["ocr_text"] = ocr_hint

    payload = {
        "model": model,
        "state": state,
        "questions": SYSTEMONE_QUESTIONS,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = httpx.post(api_url, headers=headers, json=payload, timeout=timeout_sec)
        resp.raise_for_status()
        res_json = resp.json()
    except Exception as exc:
        latency_ms = int((time.monotonic() - t0) * 1000)
        return _skip(f"typesafe-error:{exc.__class__.__name__}", latency_ms=latency_ms)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # Procesar respuestas de TypeSafe System One
    if isinstance(res_json, dict):
        answers = res_json.get("answers") or res_json.get("results") or res_json
    else:
        answers = res_json
    text_content = _format_extracted_text(answers)

    if not text_content or not text_content.strip():
        return _skip("typesafe-empty", latency_ms=latency_ms)

    # Calcular confianza
    confidence = _calculate_confidence(answers, text_content)
    min_confidence = threshold(ctx, NAME, "min_confidence", 0.6)

    feat = ExtractionFeature(
        type="pdf_text",
        extraction_method=NAME if confidence >= min_confidence else f"skipped:low-confidence-{confidence:.2f}",
        data=text_content,
        page=ctx.page_index,
        sha256=ctx.page_image_sha or "",
        extractor_version=VERSION,
        latency_ms=latency_ms,
        confidence=confidence,
    )
    ctx.cache.put(ctx.page_image_sha, feat, config_version)
    return feat


def _format_extracted_text(answers: Any) -> str:
    """Convierte las respuestas tipadas en texto legible para los extractores y el parser."""
    if isinstance(answers, str):
        return answers
    if not isinstance(answers, dict):
        return ""

    lines = []
    # Si viene texto completo en las respuestas
    if "raw_text" in answers and isinstance(answers["raw_text"], str):
        lines.append(answers["raw_text"])
    elif "content" in answers and isinstance(answers["content"], str):
        lines.append(answers["content"])
    elif "text" in answers and isinstance(answers["text"], str):
        lines.append(answers["text"])

    # Formatear campos estructurados detectados
    for k in ("nif", "iban", "total", "fecha", "pedido", "iva"):
        val = answers.get(k)
        if val is None:
            continue
        if isinstance(val, dict):
            # Formatos comunes: {"value": "...", "confidence": ...} o {"answer": "..."}
            v = val.get("value") or val.get("answer") or val.get("text") or ""
        else:
            v = str(val).strip()
        if v:
            lines.append(f"{k.upper()}: {v}")

    return "\n".join(lines)


def _calculate_confidence(answers: Any, text_content: str) -> float:
    """Calcula confianza entre 0.0 y 1.0 basada en las respuestas y cobertura."""
    if isinstance(answers, dict):
        # Si answers trae puntuaciones de confianza o probabilidades por pregunta
        confidences: list[float] = []
        for k in ("nif", "iban", "total", "fecha", "pedido", "iva"):
            val = answers.get(k)
            if isinstance(val, dict):
                c_val = val.get("confidence")
                if c_val is not None:
                    try:
                        c_float = float(c_val)
                        if not math.isnan(c_float) and not math.isinf(c_float):
                            confidences.append(max(0.0, min(1.0, c_float)))
                    except (ValueError, TypeError):
                        pass
                else:
                    # Si viene con probabilidades tipadas (p.ej. SystemOne questions)
                    probs = val.get("probabilities")
                    if isinstance(probs, dict):
                        for p in probs.values():
                            try:
                                p_float = float(p)
                                if not math.isnan(p_float) and not math.isinf(p_float):
                                    confidences.append(max(0.0, min(1.0, p_float)))
                                    break
                            except (ValueError, TypeError):
                                pass
                    elif val.get("value") or val.get("answer") or val.get("text"):
                        confidences.append(0.85)
            elif val is not None and str(val).strip():
                confidences.append(0.85)

        if confidences:
            return sum(confidences) / len(confidences)

    if text_is_plausible(text_content):
        return 0.85
    return 0.4


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
