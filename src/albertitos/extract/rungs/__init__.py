"""Escalones de la escalera de extracción. Cada módulo: NAME + extract().

Un escalón ausente (dependencia/clave/servicio) devuelve
extraction_method="skipped:<razón>" y la escalera continúa — degrada la
calidad, nunca para el lote.
"""

from . import cloud_vlm, qr, tesseract, text_layer, vlm_local

__all__ = ["cloud_vlm", "qr", "tesseract", "text_layer", "vlm_local"]
