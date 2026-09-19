"""Escalón 2: heurística de página solo-QR (regresión, con PDFs reales).

Construye PDFs con pypdfium2: uno con solo un QR y otro con solo texto.
Verifica la decisión qr_only, la confianza registrada y dónde para la escalera.
"""

from __future__ import annotations

import io

import pytest
import qrcode
from qrcode.image.pil import PilImage

pypdfium2 = pytest.importorskip("pypdfium2")
pytest.importorskip("zxingcpp")

from albertitos.extract.cache import FeatureCache
from albertitos.extract.ladder import extract_document, extract_file
from albertitos.extract.rungs.qr import _page_qr_confidence, _signal_payload_shape

_QR_PAYLOAD = (
    "https://example.com/verifactu?id=abc&IDEMISOR=B12345678&FECHA=15-01-2026"
    "&SERIE=A&IMPORTES=121.00"
)
_TEXTO = (
    "FACTURA 2026/001 Fecha: 15/01/2026 Total: 121,00 EUR Base imponible: 100,00 EUR "
    "IVA: 21,00 EUR Proveedor S.L. NIF B12345678"
)


def _pdf_with_text(path, text: str) -> None:
    stream = f"BT /F1 10 Tf 50 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    _write_pdf(path, objects)


def _pdf_qr_only(path, payload: str) -> None:
    qr = qrcode.QRCode(border=1)
    qr.add_data(payload)
    img = qr.make_image(image_factory=PilImage).convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PDF", resolution=300)
    path.write_bytes(buf.getvalue())


def _write_pdf(path, objects: list[bytes]) -> None:
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    path.write_bytes(bytes(out))


def test_payload_shape_feie_marca_alta_confianza():
    assert _signal_payload_shape([_QR_PAYLOAD]) == 1.0


def test_payload_shape_ruido_baja_confianza():
    assert _signal_payload_shape(["jkljlk"]) < 0.5


def test_heuristica_qr_only_pdf_real(tmp_path):
    pdf = tmp_path / "qr_only.pdf"
    _pdf_qr_only(pdf, _QR_PAYLOAD)
    page = pypdfium2.PdfDocument(pdf)[0]
    conf = _page_qr_confidence(page, [_QR_PAYLOAD])
    assert conf >= 0.8, f"QR-only page must clear the default 0.8 gate, got {conf}"


def test_heuristica_texto_baja_confianza(tmp_path):
    pdf = tmp_path / "text.pdf"
    _pdf_with_text(pdf, _TEXTO)
    page = pypdfium2.PdfDocument(pdf)[0]
    # sin QRs la confianza es 0 — la heurística solo puntúa páginas con QR
    assert _page_qr_confidence(page, []) == 0.0


def test_escalera_qr_only_para_en_rung2(tmp_path):
    from albertitos.config import AppConfig

    cfg = AppConfig(tmp_path / "data")
    pdf = tmp_path / "qr_only.pdf"
    _pdf_qr_only(pdf, _QR_PAYLOAD)
    pages = extract_document(pdf, FeatureCache(tmp_path / "cache"), cfg.extraction_config())
    assert pages[0].stopped_at == "zxing", "QR-only page must stop at rung 2"
    qr = [f for f in pages[0].features if f.type == "qr_payload"]
    assert qr and qr[0].confidence is not None and qr[0].confidence >= 0.8
    assert pages[0].content == _QR_PAYLOAD


def test_escalera_texto_para_en_rung1(tmp_path):
    from albertitos.config import AppConfig

    cfg = AppConfig(tmp_path / "data")
    pdf = tmp_path / "text.pdf"
    _pdf_with_text(pdf, _TEXTO)
    pages = extract_document(pdf, FeatureCache(tmp_path / "cache"), cfg.extraction_config())
    assert pages[0].stopped_at == "pypdf"


def test_imagen_entra_directo_en_rung2(tmp_path):
    """png/jpg no tienen capa de texto: la escalera empieza en el escalón 2."""
    from albertitos.config import AppConfig

    qr_img = qrcode.QRCode(border=4, box_size=10)
    qr_img.add_data("https://example.com/verifactu?id=abc&x=1")
    img = qr_img.make_image(image_factory=PilImage).convert("RGB")
    img_path = tmp_path / "factura_qr.png"
    img.save(img_path)
    cfg = AppConfig(tmp_path / "data")
    pages = extract_file(img_path, FeatureCache(tmp_path / "cache"), cfg.extraction_config())
    assert len(pages) == 1
    # ninguna feature pypdf: el escalón 1 se saltó por completo
    assert all(f.extraction_method != "pypdf" for f in pages[0].features)
    # el QR se leyó y su payload es el contenido de la "página"
    qr = [f for f in pages[0].features if f.type == "qr_payload"]
    assert qr and pages[0].content
