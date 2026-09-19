"""Preprocesamiento y mejora de imágenes para escaneos degradados.

Pipeline adaptativo para rescate de scans ruidosos, borrosos o de bajo contraste:
1. Decodificación de bytes a imagen OpenCV.
2. Conversión a escala de grises.
3. Normalización / estiramiento de contraste (cv2.normalize [0, 255]).
4. Unsharp masking (filtro gaussiano + combinación ponderada) para perfilar
   números tenues, comas y puntos decimales.
5. Retorno en bytes PNG.
"""

from __future__ import annotations

try:
    import cv2
    import numpy as np
    _HAS_CV2 = True
except ImportError:
    _HAS_CV2 = False
def enhance_scan_image(image_bytes: bytes) -> bytes:
    """Mejora y perfilar un escaneo degradado usando OpenCV.

    Args:
        image_bytes: Bytes del archivo de imagen (PNG, JPEG, etc.).

    Returns:
        Bytes PNG de la imagen procesada y perfilada.
    """
    if not image_bytes or not _HAS_CV2:
        return image_bytes

    # 1. Decodificar imagen desde bytes
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return image_bytes

    # 2. Convertir a escala de grises
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 3. Estiramiento de contraste dinámico a rango completo [0, 255]
    norm = cv2.normalize(gray, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)

    # 4. Unsharp masking: perfilar detalles finos (números tenues, comas, puntos)
    # blurred = GaussianBlur(norm, (0, 0), sigmaX=3.0)
    # sharpened = 1.5 * norm - 0.5 * blurred
    blurred = cv2.GaussianBlur(norm, (0, 0), sigmaX=3.0)
    sharpened = cv2.addWeighted(norm, 1.5, blurred, -0.5, 0)

    # 5. Codificar de vuelta a PNG
    success, encoded = cv2.imencode(".png", sharpened)
    if not success:
        return image_bytes

    return encoded.tobytes()
