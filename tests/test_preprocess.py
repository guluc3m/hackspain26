"""Tests unitarios para preprocesamiento de imágenes de escaneos degradados."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest
from PIL import Image as PILImage

from filemaid.extract.cache import FeatureCache, sha256_bytes
from filemaid.extract.preprocess import enhance_scan_image
from filemaid.extract.rungs import vlm_local
from filemaid.extract.rungs.context import PageContext


def _create_synthetic_scan(width: int = 100, height: int = 100, low_contrast: bool = True) -> bytes:
    """Crea una imagen sintética en memoria simulando scan tenue."""
    if low_contrast:
        # Rango comprimido de grises (ej. 100 a 140) simulando escaneo pálido
        img_arr = np.random.randint(100, 140, (height, width, 3), dtype=np.uint8)
        # Dibujar líneas o "caracteres" tenues
        img_arr[30:70, 20:30] = 95
        img_arr[40:50, 40:80] = 145
    else:
        img_arr = np.full((height, width, 3), 255, dtype=np.uint8)
        img_arr[20:80, 20:80] = 0

    success, buf = cv2.imencode(".png", img_arr)
    assert success
    return buf.tobytes()


def test_enhance_scan_image_empty_input():
    assert enhance_scan_image(b"") == b""


def test_enhance_scan_image_invalid_bytes():
    corrupt = b"not_a_valid_image_header"
    assert enhance_scan_image(corrupt) == corrupt


def test_enhance_scan_image_contrast_and_sharpening():
    raw_png = _create_synthetic_scan(low_contrast=True)
    enhanced_png = enhance_scan_image(raw_png)

    assert enhanced_png != raw_png
    assert len(enhanced_png) > 0

    # Decodificar ambas para comparar rango dinámico
    raw_mat = cv2.imdecode(np.frombuffer(raw_png, np.uint8), cv2.IMREAD_GRAYSCALE)
    enhanced_mat = cv2.imdecode(np.frombuffer(enhanced_png, np.uint8), cv2.IMREAD_GRAYSCALE)

    # La imagen original tiene rango dinámico estrecho
    raw_min, raw_max = int(raw_mat.min()), int(raw_mat.max())
    assert raw_max - raw_min < 100

    # La imagen normalizada y perfilada cubre rango completo [0, 255]
    enh_min, enh_max = int(enhanced_mat.min()), int(enhanced_mat.max())
    assert enh_min == 0
    assert enh_max == 255

    # Verificar que es PNG válido
    pil_img = PILImage.open(io.BytesIO(enhanced_png))
    assert pil_img.format == "PNG"


def test_vlm_local_multi_pass_rescues_low_coverage(tmp_path: Path):
    """Verifica que vlm_local realiza multi-pass si el primer intento tiene baja cobertura."""
    cache = FeatureCache(tmp_path / "cache")
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)

    raw_png = _create_synthetic_scan(low_contrast=True)
    (pages_dir / "p0.png").write_bytes(raw_png)

    ctx = PageContext(
        pdf_path=tmp_path / "scan_degraded.pdf",
        page_index=0,
        cache=cache,
        config={"config_version": "v1"},
        pages_dir=pages_dir,
        page_image_sha="sha_degraded_test_1",
    )

    mock_mgr = MagicMock()
    mock_mgr.ensure_started.return_value = True
    mock_mgr.base_url = "http://127.0.0.1:8080"

    # Primer pase: texto incompleto / baja cobertura
    # Segundo pase (con imagen realzada): texto completo con NIF, Total, IVA, Fecha
    responses = [
        # 1er llamado: texto con baja cobertura de campos
        MagicMock(status_code=200, json=lambda: {
            "choices": [{"message": {"content": "algun texto borroso sin campos clave"}}]
        }, raise_for_status=lambda: None),
        # 2do llamado (multi-pass con imagen preprocesada): texto rescatado
        MagicMock(status_code=200, json=lambda: {
            "choices": [{"message": {"content": (
                "FACTURA 2026/0477 Fecha: 08/03/2026 Total: 1.292,88 EUR "
                "Base imponible: 1.068,50 EUR IVA 21%: 224,38 EUR Proveedor S.L. NIF B12345678"
            )}}]
        }, raise_for_status=lambda: None),
    ]

    with patch("filemaid.llama_manager.get_manager", return_value=mock_mgr):
        with patch("httpx.post", side_effect=responses) as mock_post:
            feat = vlm_local.extract(ctx)

    assert mock_post.call_count == 2
    assert feat.extraction_method == "vlm"
    assert feat.confidence >= 0.5
    assert "FACTURA 2026/0477" in feat.data
    assert feat.extractor_version == vlm_local.VERSION

    # Verificar que el resultado quedó en caché
    cached = cache.get("sha_degraded_test_1", vlm_local.VERSION, "v1")
    assert cached is not None
    assert cached.data == feat.data
