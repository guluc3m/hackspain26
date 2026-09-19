"""Regresión: las imágenes de /revision se sirven por endpoint, no en base64
dentro del HTML (el HTML pesaba decenas de MB y el navegador no acababa)."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from albertitos.ui.app import create_app

PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
        "0000000d4944415478da63fcffff3f030005fe02fea72d3eb40000000049454e44ae426082"
    )
).decode()


def _records() -> list[dict]:
    return [
        {
            "kind": "fields",
            "invoice_id": "inv-1",
            "file_id": "factura_1.pdf",
            "fields": {"total": [{"extractor": "pypdf", "value": 10, "confidence": 0.9}]},
            "page_images": {"1": PNG_1PX},
        },
        {
            "kind": "decision",
            "invoice_id": "inv-1",
            "file_id": "factura_1.pdf",
            "result": "ESCALAR",
            "rule_verdicts": [{"code": "NIF_IN_MASTER", "outcome": "UNKNOWN", "reason": "sin NIF"}],
            "config_snapshot": {},
        },
    ]


def test_revision_sirve_imagen_por_endpoint():
    """El HTML ya NO lleva megas de base64: el <img> apunta al endpoint y el
    endpoint devuelve el PNG real (indexado por invoice_id y por file_id)."""
    with TestClient(create_app(records=_records())) as c:
        html = c.get("/revision").text
        assert 'src="/revision/imagen/inv-1/1"' in html
        assert "base64," not in html
        r = c.get("/revision/imagen/inv-1/1")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"
        assert r.content.startswith(b"\x89PNG")
        # alias por file_id (el join real de la UI usa file_id)
        assert c.get("/revision/imagen/factura_1.pdf/1").status_code == 200
        assert c.get("/revision/imagen/inv-1/99").status_code == 404


def test_revision_sin_imagen_muestra_aviso_y_404():
    with TestClient(create_app(records=[dict(_records()[0], page_images={})])) as c:
        html = c.get("/revision").text
        assert "Sin imagen almacenada" in html
        assert c.get("/revision/imagen/inv-1/1").status_code == 404
