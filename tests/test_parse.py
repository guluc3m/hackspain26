"""Tests del parser (T2): features → campos con candidatos."""

from __future__ import annotations

import hashlib

from pypdf import PdfReader

from albertitos.parse import field_by_type, parse_invoice
from albertitos.parse.normalizers import (
    parse_amount,
    parse_amount_float,
    parse_fecha,
    validate_iban,
    validate_nif,
)
from albertitos.types import ExtractionFeature
from conftest import fixture_path

FIXTURES = ("invoice_catering_fa8496.pdf", "invoice_mensajeria_fa7399.pdf",
            "invoice_dup_fa8801_p005.pdf")


def _feature_from_pdf(name: str) -> ExtractionFeature:
    path = fixture_path("facturas", name)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    return ExtractionFeature(
        type="pdf_text",
        extraction_method="pypdf",
        timestamp=0.0,
        data=text,
        sha256=hashlib.sha256(text.encode()).hexdigest(),
    )


def _parse_fixture(name: str) -> dict[str, object]:
    fields = parse_invoice([_feature_from_pdf(name)])
    return {f.type: f for f in fields}


# ---------------------------------------------------------------- normalizers


from decimal import Decimal


def test_importe_espanol_punto_miles_coma_decimal_exacto():
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert parse_amount_float("1.234,56") == 1234.56
    assert parse_amount_float("12.874,40") == 12874.40
    assert parse_amount_float("84700") == 84700.0
    # formato anglosajón también aceptado como candidato
    assert parse_amount_float("1700.00") == 1700.00
    assert parse_amount_float("1.234") == 1234.0  # punto de miles español
    assert parse_amount("no-es-un-importe") is None


def test_fecha_formatos():
    assert parse_fecha("Fecha: 08/04/2026") == "2026-04-08"
    assert parse_fecha("25 de enero de 2026") == "2026-01-25"
    assert parse_fecha("22 de febrero de 2026") == "2026-02-22"
    assert parse_fecha("31/02/2026") is None  # fecha imposible
    assert parse_fecha("sin fecha aqui") is None


def test_fecha_invalida_no_anula_las_siguientes_T38F4():
    """La 1ª fecha inválida NO anula el campo: la 1ª VÁLIDA manda."""
    assert parse_fecha("30/02/2026, factura 05/03/2026") == "2026-03-05"
    assert parse_fecha("31/04/2026 vence 01/05/2026") == "2026-05-01"
    # la inválida no genera valor; si SOLO hay inválidas, None (igual que antes)
    assert parse_fecha("31/02/2026, 32/13/2026") is None
    # el texto en meses sigue funcionando y también salta inválidas
    assert parse_fecha("30 de febrero de 2026 · 5 de marzo de 2026") == "2026-03-05"


def test_nif_letra_de_control():
    assert validate_nif("B46102331")  # empresa: formato válido
    assert validate_nif("A46311208")
    assert not validate_nif("B12")  # demasiado corto
    assert not validate_nif("XX12345678")
    # persona física: letra de control mod 23
    assert validate_nif("12345678Z")
    assert not validate_nif("12345678A")


def test_iban_mod97():
    # Validador mod-97 como señal de confianza, nunca veto (T2).
    assert validate_iban("ES91 2100 0418 4502 0005 1332")  # IBAN real válido
    assert not validate_iban("ES18 0081 5290 0700 0123 4568")  # dígito mal
    assert not validate_iban("ES00 0081 5290 0700 0123 4567")  # check mal


# ---------------------------------------------------------------- parser


def test_parser_emite_todos_los_campos_con_confianza_valida():
    fields = parse_invoice([_feature_from_pdf(FIXTURES[0])])
    tipos = {f.type for f in fields}
    esperados = {"nif", "iban", "fecha", "pedido", "base", "iva_pct",
                 "iva_amount", "total", "proveedor", "numero_factura"}
    assert esperados <= tipos
    for f in fields:
        assert len(f.values) >= 1
        for c in f.values:
            assert 0.0 <= c.confidence <= 1.0
            assert c.feature_ref.startswith("pdf_text:")


def test_parser_formato_espanol_exacto_catering():
    fields = parse_invoice([_feature_from_pdf(FIXTURES[0])])
    assert field_by_type(fields, "base").values[0].value == 2022.10
    assert field_by_type(fields, "iva_amount").values[0].value == 424.64
    assert field_by_type(fields, "total").values[0].value == 2446.74
    assert field_by_type(fields, "iva_pct").values[0].value == 21
    assert field_by_type(fields, "nif").values[0].value == "B96233419"
    assert field_by_type(fields, "iban").values[0].value == "ES1800815290070001234567"
    assert field_by_type(fields, "fecha").values[0].value == "2026-01-25"
    assert field_by_type(fields, "pedido").values[0].value == "PO-2026-0099"
    assert field_by_type(fields, "numero_factura").values[0].value == "FA-8496"


def test_parser_formato_mensajeria():
    fields = parse_invoice([_feature_from_pdf(FIXTURES[1])])
    assert field_by_type(fields, "base").values[0].value == 8190.64
    assert field_by_type(fields, "iva_amount").values[0].value == 1720.03
    assert field_by_type(fields, "total").values[0].value == 9910.67
    assert field_by_type(fields, "nif").values[0].value == "B90233808"
    assert field_by_type(fields, "proveedor").values[0].value == "Mensajería Rápida del Sur S.L."


def test_parser_no_confunde_nif_del_cliente():
    fields = parse_invoice([_feature_from_pdf(FIXTURES[1])])
    nifs = [c.value for c in field_by_type(fields, "nif").values]
    assert "A58231074" not in nifs  # CIF del cliente (Banco Miralmar)


def test_dos_extractores_en_desacuerdo_dos_candidatos_ninguno_descartado():
    texto = _feature_from_pdf(FIXTURES[0]).data
    # Segundo extractor (OCR simulado) lee otro NIF: el parser conserva ambos.
    f1 = _feature_from_pdf(FIXTURES[0])
    f2 = ExtractionFeature(
        type="ocr_text", extraction_method="tesseract", timestamp=1.0,
        data=texto.replace("B96233419", "B96233410"), sha256="ocr-sha",
    )
    fields = parse_invoice([f1, f2])
    nif = field_by_type(fields, "nif")
    valores = {c.value for c in nif.values}
    assert {"B96233419", "B96233410"} <= set(valores)
    assert {"regex-nif"} <= extractores_vistos(nif)
    assert len(nif.values) >= 2


def extractores_vistos(field):
    return {c.extractor for c in field.values}


def test_campo_ausente_devuelve_none():
    fields = parse_invoice([_feature_from_pdf(FIXTURES[0])])
    assert field_by_type(fields, "campo_inexistente") is None


def test_feature_vacia_no_explota():
    f = ExtractionFeature(type="pdf_text", extraction_method="pypdf",
                          timestamp=0.0, data="")
    assert parse_invoice([f]) == []


def test_determinismo_parser():
    feats = [_feature_from_pdf(n) for n in FIXTURES]
    a = [repr(f) for f in parse_invoice(feats)]
    b = [repr(f) for f in parse_invoice(feats)]
    assert a == b


def test_todos_los_candidatos_referencian_feature():
    f1 = _feature_from_pdf(FIXTURES[0])
    f2 = _feature_from_pdf(FIXTURES[1])
    for field in parse_invoice([f1, f2]):
        refs = {c.feature_ref for c in field.values}
        assert refs <= {
            f"pdf_text:{hashlib.sha256(f1.data.encode()).hexdigest()[:16]}",
            f"pdf_text:{hashlib.sha256(f2.data.encode()).hexdigest()[:16]}",
        }


def test_fixtures_scan_sin_texto_producen_campos_vacios():
    """Los scans sin capa de texto no deben inventar campos."""
    for name in ("scan_001.pdf", "scan_002.pdf"):
        reader = PdfReader(fixture_path("scans", name))
        texto = "\n".join(p.extract_text() or "" for p in reader.pages)
        fields = parse_invoice([ExtractionFeature(
            type="pdf_text", extraction_method="pypdf", timestamp=0.0, data=texto,
        )])
        assert fields == []