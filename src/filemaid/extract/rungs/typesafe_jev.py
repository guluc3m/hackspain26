"""Escalón 5: juicios tipados de TypeSafe sobre texto previo, nunca OCR.

Conserva la respuesta completa como evidencia; no produce campos de factura ni
resuelve la página. Cachea sobre (page_image_sha, VERSION, config_version).
"""

from __future__ import annotations

import math
import os
import time
from typing import Any

import httpx

from filemaid.store.trace import capture_response
from filemaid.types import ExtractionFeature

from .context import PageContext

NAME = "typesafe_jev"
VERSION = "typesafe_jev-2"

_DEFAULT_API_URL = "https://api.typesafe.ai/v1/systemone"
_DEFAULT_MODEL = "jev-latest"

SYSTEMONE_QUESTIONS: dict[str, dict[str, Any]] = {
    "is_invoice": {
        "type": "noul",
        "instructions": "¿El texto corresponde a una factura o justificante de gasto comercial?",
    },
    "has_fiscal_data": {
        "type": "noul",
        "instructions": "¿El texto contiene datos fiscales explícitos del emisor e importes desglosados?",
    },
    "document_quality": {
        "type": "score",
        "instructions": "Evalúa la legibilidad y completitud del texto disponible, no la validez de pago.",
        "criteria": [
            "Texto ilegible o sin información documental utilizable",
            "Texto parcialmente legible o incompleto",
            "Texto legible con información documental suficiente",
        ],
    },
    "document_category": {
        "type": "choice",
        "instructions": "Clasifica el documento según el texto disponible.",
        "criteria": {
            "invoice": "Factura comercial",
            "receipt": "Ticket o justificante de gasto",
            "other": "Otro documento o contenido insuficiente para clasificarlo",
        },
    },
}


def _get_setting(
    ctx: PageContext, keys: tuple[str, ...], env_var: str, default: Any = ""
) -> Any:
    """La configuración explícita del escalón prima sobre los defaults globales."""
    for settings in (ctx.config.get("rungs", {}).get(NAME, {}), ctx.config):
        for key in keys:
            value = settings.get(key)
            if value is not None and value != "":
                return value
    return os.environ.get(env_var, default)


def extract(ctx: PageContext) -> ExtractionFeature:
    t0 = time.monotonic()

    if ctx.page_image_sha is None:
        return _skip(ctx, "no-page-image", t0)
    api_key = _get_setting(ctx, ("api_key", "typesafe_api_key"), "TYPESAFE_API_KEY")
    if not api_key:
        return _skip(ctx, "no-typesafe-api-key", t0)
    if not ctx.ocr_text.strip():
        return _skip(ctx, "typesafe-no-ocr-text", t0)

    config_version = ctx.config.get("config_version", "")
    cached = ctx.cache.get(ctx.page_image_sha, VERSION, config_version)
    if cached is not None:
        return cached

    api_url = str(_get_setting(
        ctx, ("endpoint", "typesafe_api_url"), "TYPESAFE_API_URL", _DEFAULT_API_URL
    )).rstrip("/")
    model = str(_get_setting(ctx, ("model", "typesafe_model"), "TYPESAFE_MODEL", _DEFAULT_MODEL))
    timeout_sec = float(_get_setting(ctx, ("timeout",), "TYPESAFE_TIMEOUT", 60.0))
    payload = {
        "model": model,
        "state": {"ocr_text": ctx.ocr_text, "page_index": ctx.page_index},
        "questions": SYSTEMONE_QUESTIONS,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = None
    try:
        resp = httpx.post(api_url, headers=headers, json=payload, timeout=timeout_sec)
        resp.raise_for_status()
        response = resp.json()
    except Exception as exc:
        return _skip(ctx, f"typesafe-error:{exc.__class__.__name__}", t0)
    finally:
        if resp is not None:
            capture_response(NAME, resp)

    confidence = _evidence_confidence(response)
    if confidence is None:
        return _skip(ctx, "typesafe-malformed-response", t0)

    feat = ExtractionFeature(
        type="typed_evidence",
        extraction_method=NAME,
        data=response,
        page=ctx.page_index,
        sha256=ctx.page_image_sha,
        extractor_version=VERSION,
        latency_ms=int((time.monotonic() - t0) * 1000),
        confidence=confidence,
    )
    ctx.cache.put(ctx.page_image_sha, feat, config_version)
    return feat


def _finite_number(value: Any, low: float, high: float) -> bool:
    return (
        type(value) in (int, float)
        and low <= value <= high
        and math.isfinite(value)
    )


def _evidence_confidence(response: Any) -> float | None:
    """Valida las respuestas solicitadas; confianza del juicio, no del pago."""
    if not isinstance(response, dict) or not isinstance(response.get("model"), str):
        return None
    usage = response.get("usage")
    if not isinstance(usage, dict) or any(
        type(usage.get(key)) is not int or usage[key] < 0
        for key in ("input_tokens", "output_tokens")
    ):
        return None
    answers = response.get("answers")
    if not isinstance(answers, dict):
        return None
    confidences = []
    for name, question in SYSTEMONE_QUESTIONS.items():
        answer = answers.get(name)
        if not isinstance(answer, dict) or answer.get("type") != question["type"]:
            return None
        if question["type"] == "noul":
            probability = answer.get("noul")
            if not _finite_number(probability, 0.0, 1.0):
                return None
            confidences.append(max(probability, 1.0 - probability))
            continue
        confidence = answer.get("confidence")
        probabilities = answer.get("probabilities")
        if not _finite_number(confidence, 0.0, 1.0) or not isinstance(probabilities, dict):
            return None
        if not probabilities or not all(_finite_number(p, 0.0, 1.0) for p in probabilities.values()):
            return None
        if question["type"] == "choice":
            choice = answer.get("choice")
            if not isinstance(choice, str) or choice not in question["criteria"]:
                return None
            if set(probabilities) != set(question["criteria"]):
                return None
        else:
            levels = {str(i) for i in range(len(question["criteria"]))}
            legend = answer.get("legend")
            if not isinstance(legend, dict) or set(legend) != levels or set(probabilities) != levels:
                return None
            if not _finite_number(answer.get("score"), 0.0, len(levels) - 1):
                return None
        confidences.append(confidence)
    return sum(confidences) / len(confidences)


def _skip(ctx: PageContext, reason: str, started: float) -> ExtractionFeature:
    return ExtractionFeature(
        type="typed_evidence",
        extraction_method=f"skipped:{reason}",
        page=ctx.page_index,
        sha256=ctx.page_image_sha or "",
        extractor_version=VERSION,
        latency_ms=int((time.monotonic() - started) * 1000),
    )
