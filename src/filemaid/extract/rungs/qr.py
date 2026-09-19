"""Escalón 2: rasterizado (pypdfium2) + decodificación de QR (zxing-cpp).

Rinde DOS features: la imagen de página (para la cola de revisión) y el
payload QR si lo hay — nunca se colapsan (architecture.typ §2: la ambigüedad
es señal). Página solo-QR (confianza ≥ umbral) ⇒ el payload es el contenido
y la escalera para aquí; el payload es dato no confiado, jamás instrucciones.
"""

from __future__ import annotations

import io
import re
import time
from dataclasses import dataclass, field
from typing import Any

from filemaid.types import ExtractionFeature

from ..cache import sha256_bytes
from .context import PageContext, threshold

NAME = "zxing"
VERSION = "1"

try:
    import pypdfium2 as pdfium
except ImportError:  # pragma: no cover
    pdfium = None

try:
    import zxingcpp
except ImportError:  # pragma: no cover
    zxingcpp = None


@dataclass(slots=True)
class QrRungResult:
    features: list[ExtractionFeature] = field(default_factory=list)
    page_image_sha: str | None = None
    qr_only: bool = False
    content: str = ""


def extract(ctx: PageContext) -> QrRungResult:
    t0 = time.monotonic()
    page: Any | None = None
    if ctx.pdf_path.suffix.lower() == ".pdf":
        if pdfium is None:
            return QrRungResult([_skip("dep:pypdfium2", latency_ms=int((time.monotonic() - t0) * 1000))])
        page = pdfium.PdfDocument(ctx.pdf_path)[ctx.page_index]
        img = page.render(scale=ctx.config.get("render_scale", 2.0)).to_pil()
    else:
        # imagen suelta (png/jpg/...): el rasterizado ES la propia imagen
        try:
            from PIL import Image as PILImage

            img = PILImage.open(ctx.pdf_path).convert("RGB")
        except Exception:
            return QrRungResult([_skip("dep:pillow", latency_ms=int((time.monotonic() - t0) * 1000))])

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    page_sha = sha256_bytes(png_bytes)
    ctx.page_image_sha = page_sha

    if ctx.pages_dir is not None:
        out = ctx.pages_dir / f"p{ctx.page_index}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png_bytes)

    image_latency = int((time.monotonic() - t0) * 1000)
    image_feature = ExtractionFeature(
        type="page_image",
        extraction_method="pypdfium2",
        data=page_sha,
        page=ctx.page_index,
        sha256=page_sha,
        extractor_version=VERSION,
        latency_ms=image_latency,
    )

    if zxingcpp is None:
        return QrRungResult([image_feature], page_image_sha=page_sha)

    t_qr = time.monotonic()
    payloads: list[str] = []
    try:
        for result in zxingcpp.read_barcodes(img):
            payloads.append(result.text)
    except Exception:
        pass

    if not payloads:
        return QrRungResult([image_feature], page_image_sha=page_sha)

    confidence = _page_qr_confidence(page, payloads, img_size=img.size)
    qr_latency = int((time.monotonic() - t_qr) * 1000)
    qr_feature = ExtractionFeature(
        type="qr_payload",
        extraction_method=NAME,
        data=payloads,
        page=ctx.page_index,
        sha256=page_sha,
        extractor_version=VERSION,
        confidence=confidence,
        latency_ms=qr_latency,
    )
    qr_only = confidence >= threshold(ctx, "qr", "qr_only_confidence", 0.8)
    content = payloads[0] if qr_only else ""
    return QrRungResult(
        [image_feature, qr_feature], page_image_sha=page_sha, qr_only=qr_only, content=content
    )


def _page_qr_confidence(page: Any, payloads: list[str], img_size: tuple[int, int] | None = None) -> float:
    """Confianza [0,1] en que esta página ES solo-QR (el payload es el contenido).

    Tres señales independientes, media aritmética:
      1. Estructura: sin objetos de texto (o imagen suelta, sin PDF) ⇒ nada que OCR lea.
      2. Cobertura: los QRs dominan el área de la página (son "la" página).
      3. Payload: aspecto de datos estructurados de factura (URL, key=value,
         o el formato FEIE/Veri*factu), no ruido.
    """
    if not payloads:
        return 0.0
    signals = [
        _signal_no_text(page),
        _signal_qr_coverage(page, payloads, img_size=img_size),
        _signal_payload_shape(payloads),
    ]
    return sum(signals) / len(signals)


def _signal_no_text(page: Any) -> float:
    """1.0 si la página no tiene ningún objeto de texto (nada que OCR lea)."""
    if page is None:  # imagen suelta: no hay capa de texto
        return 1.0
    try:
        return 0.0 if page.get_textpage().count_chars() > 0 else 1.0
    except Exception:
        return 0.5  # no inspeccionable ⇒ neutral, no sesga


def _signal_qr_coverage(
    page: Any, payloads: list[str], img_size: tuple[int, int] | None = None
) -> float:
    """Fracción de la página cubierta por los QRs, saturada en 1.0."""
    try:
        if page is None:
            if img_size is None:
                return 0.5
            page_w, page_h = img_size
            # una imagen suelta: si zxing leyó algo, la imagen ES el QR;
            # aproximar por proporción no es fiable ⇒ señal generosa
            return 1.0
        page_w, page_h = page.get_size()
        page_area = page_w * page_h
        if page_area <= 0:
            return 0.5
        qr_area = 0.0
        for obj in page.get_objects():
            if obj.type != 3:  # FPDF_PAGEOBJ_IMAGE
                continue
            l, b, r, t = obj.get_bounds()
            qr_area += max(0.0, r - l) * max(0.0, t - b)
        return min(1.0, qr_area / page_area / _QR_COVERAGE_FULL)
    except Exception:
        return 0.5


def _signal_no_text(page: Any) -> float:
    """1.0 si la página no tiene ningún objeto de texto (nada que OCR lea)."""
    try:
        return 0.0 if page.get_textpage().count_chars() > 0 else 1.0
    except Exception:
        return 0.5  # no inspeccionable ⇒ neutral, no sesga



def _signal_payload_shape(payloads: list[str]) -> float:
    """Aspecto de datos estructurados: URL de factura, key=value o FEIE/Veri*factu."""
    p = payloads[0]
    if _FEIE_MARKERS <= set(p.upper().split("&")) or _FEIE_RE.search(p):
        return 1.0  # formato normativo conocido
    score = 0.0
    if p[:8].lower() in ("http://", "https://"):
        score += 0.6
    if "=" in p and "&" in p:
        score += 0.3
    elif "=" in p:
        score += 0.2
    if any(ch.isdigit() for ch in p):
        score += 0.1
    return min(1.0, score)


_FEIE_MARKERS = {"NIF", "IDEMISOR", "FECHA", "SERIE", "IMPORTES"}  # Veri*factu (RD 1007/2023)
_FEIE_RE = re.compile(r"(?i)feie|verifactu|facturae")
_QR_COVERAGE_FULL = 0.6  # los QRs ≥60% del área ⇒ son la página entera


def _skip(reason: str, latency_ms: int = 0) -> ExtractionFeature:
    return ExtractionFeature(
        type="page_image",
        extraction_method=f"skipped:{reason}",
        extractor_version=VERSION,
        latency_ms=latency_ms,
    )
