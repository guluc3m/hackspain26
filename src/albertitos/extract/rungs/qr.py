"""Escalón 2: rasterizado (pypdfium2) + decodificación de QR (zxing-cpp).

- Página cuyo único contenido son QRs: el payload es el contenido, parar.
- QRs conviviendo con más contenido: se guarda el payload y se continúa.
- El payload es *dato no fiable*, nunca instrucciones.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from albertitos.types import ExtractionFeature

from ..cache import FeatureCache, sha256_bytes

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
    feature: ExtractionFeature
    page_image_sha: str | None = None
    qr_only: bool = False
    content: str = ""


def extract(
    pdf_path: Path,
    page_index: int,
    cache: FeatureCache,
    config: dict[str, Any],
    pages_dir: Path | None = None,
) -> QrRungResult:
    if pdfium is None:
        return QrRungResult(_skip("dep:pypdfium2"))

    page = pdfium.PdfDocument(pdf_path)[page_index]
    bitmap = page.render(scale=config.get("render_scale", 2.0))
    img = bitmap.to_pil()
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    page_sha = sha256_bytes(png_bytes)

    if pages_dir is not None:
        out = pages_dir / f"p{page_index}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png_bytes)

    feature = ExtractionFeature(
        type="page_image",
        extraction_method="pypdfium2",
        data=page_sha,
        page=page_index,
        sha256=page_sha,
        extractor_version=VERSION,
    )

    if zxingcpp is None:
        return QrRungResult(_coalesce(feature, _skip("dep:zxing-cpp")), page_image_sha=page_sha)

    payloads: list[str] = []
    try:
        for result in zxingcpp.read_barcodes(img):
            payloads.append(result.text)
    except Exception:
        pass

    qr_feature = ExtractionFeature(
        type="qr_payload",
        extraction_method=NAME,
        data=payloads,
        page=page_index,
        sha256=page_sha,
        extractor_version=VERSION,
    )
    qr_only = bool(payloads) and not _has_other_content(page)
    content = payloads[0] if (qr_only and payloads) else ""
    return QrRungResult(_coalesce(feature, qr_feature), page_image_sha=page_sha, qr_only=qr_only, content=content)


def _has_other_content(page: Any) -> bool:
    """TODO: heurística real (nº de objetos de texto/vectoriales vs. solo imágenes)."""
    return True


def _coalesce(image_feature: ExtractionFeature, qr_feature: ExtractionFeature) -> ExtractionFeature:
    # El rasterizado siempre ocurre; el QR se adjunta como detalle en `data` compuesto.
    if qr_feature.extraction_method.startswith("skipped"):
        return image_feature
    return qr_feature


def _skip(reason: str) -> ExtractionFeature:
    return ExtractionFeature(type="page_image", extraction_method=f"skipped:{reason}", extractor_version=VERSION)
