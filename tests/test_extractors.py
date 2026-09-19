from __future__ import annotations

import pytest

from albertitos.parse.extractors import (
    all_extractors,
    _base,
    _fecha,
    _iban,
    _iva_amount,
    _iva_rate,
    _nif,
    _pedido,
    _total,
)
from albertitos.rules.escoger import FORMAT_TESTS


class TestFechaExtractor:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("15 de enero de 2026", "15/01/2026"),
            ("1 de abril de 2026", "01/04/2026"),
            ("22 de febrero de 2026", "22/02/2026"),
            ("31 de diciembre de 2025", "31/12/2025"),
            ("5 de mayo de 2026", "05/05/2026"),
            ("Fecha: 10 de octubre de 2026", "10/10/2026"),
            ("Madrid, a 18 de julio de 2026", "18/07/2026"),
        ],
    )
    def test_fechas_naturales(self, raw: str, expected: str):
        val, conf = _fecha(raw)
        assert val == expected
        assert conf > 0.0
        assert FORMAT_TESTS["DATE_FORMAT"](val)

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("15/01/2026", "15/01/2026"),
            ("01/04/2026", "01/04/2026"),
            ("22-02-2026", "22-02-2026"),
            ("15.01.2026", "15.01.2026"),
            ("1/4/26", "1/4/26"),
            ("Fecha: 20/11/2025", "20/11/2025"),
        ],
    )
    def test_fechas_numericas(self, raw: str, expected: str):
        val, conf = _fecha(raw)
        assert val == expected
        assert conf > 0.0
        assert FORMAT_TESTS["DATE_FORMAT"](val)

    def test_fecha_invalida_retorna_none(self):
        val, conf = _fecha("sin fecha presente")
        assert val is None
        assert conf == 0.0


class TestIvaExtractors:
    @pytest.mark.parametrize(
        ("text", "expected_rate", "expected_amount"),
        [
            ("I.V.A. (21%): 188,60", 21, 188.60),
            ("IVA (21%): 522,90", 21, 522.90),
            ("Cuota IVA: EUR 413,61", None, 413.61),
            ("IVA.......... 181,80", None, 181.80),
            ("IVA 21% 522,90", 21, 522.90),
            ("I.V.A. 21%: 188,60 €", 21, 188.60),
            ("Cuota I.V.A. (10%): 45,50", 10, 45.50),
            ("I.V.A. ... 21% ... 1.250,50 €", 21, 1250.50),
        ],
    )
    def test_iva_variaciones_puntuacion(
        self, text: str, expected_rate: int | None, expected_amount: float | None
    ):
        rate_val, rate_conf = _iva_rate(text)
        amt_val, amt_conf = _iva_amount(text)

        if expected_rate is not None:
            assert rate_val == expected_rate
            assert rate_conf > 0.0
        if expected_amount is not None:
            assert amt_val == expected_amount
            assert amt_conf > 0.0
            assert FORMAT_TESTS["AMOUNT_NON_NEGATIVE"](amt_val)

    def test_iva_sin_datos(self):
        val, conf = _iva_rate("Factura sin cuota")
        assert val is None and conf == 0.0
        val, conf = _iva_amount("Factura sin cuota")
        assert val is None and conf == 0.0


class TestIbanExtractor:
    @pytest.mark.parametrize(
        "iban_con_zw",
        [
            "ES12\u200b3456\u200c7890\ufeff1234\u200d56789012",
            "ES91\u200b2100\u200b0418\u200b4502\u200b0005\u200b1332",
            "ES91 2100 0418 4502 0005 1332",
            "IBAN: ES9121000418450200051332",
            "ES91\ufeff2100\u200c0418\u200b4502\u200d0005\ufeff1332",
        ],
    )
    def test_iban_zero_width_chars(self, iban_con_zw: str):
        val, conf = _iban(iban_con_zw)
        assert val is not None
        assert conf > 0.0
        assert FORMAT_TESTS["IBAN_FORMAT"](val)

    def test_iban_invalido(self):
        val, conf = _iban("Cuenta no bancaria 12345")
        assert val is None
        assert conf == 0.0


class TestPedidoExtractor:
    @pytest.mark.parametrize(
        ("text", "expected_pedido"),
        [
            ("PO: PO-2026-0222", "PO-2026-0222"),
            ("PEDIDO CLIENTE: PO-2026-0144", "PO-2026-0144"),
            ("Pedido cliente: PO-2026-0144", "PO-2026-0144"),
            ("Su pedido: PO-2026-0070", "PO-2026-0070"),
            ("su pedido: PO-2026-0070", "PO-2026-0070"),
            ("REF. PEDIDO: PO-2026-0266", "PO-2026-0266"),
            ("Ref. Pedido: PO-2026-0266", "PO-2026-0266"),
            ("Pedido asociado: PO-2026-0220", "PO-2026-0220"),
            ("Nº Pedido: PO-2026-0999", "PO-2026-0999"),
            ("Nº. PEDIDO: P-2026-001", "P-2026-001"),
            ("ORDEN: PO-2026-0100", "PO-2026-0100"),
            ("Factura con PO-2026-0055 en el texto", "PO-2026-0055"),
        ],
    )
    def test_pedido_variaciones(self, text: str, expected_pedido: str):
        val, conf = _pedido(text)
        assert val == expected_pedido
        assert conf > 0.0
        assert FORMAT_TESTS["PEDIDO_FORMAT"](val)

    def test_pedido_sin_coincidencia(self):
        val, conf = _pedido("Factura de servicios generales")
        assert val is None
        assert conf == 0.0


class TestTotalBaseExtractors:
    @pytest.mark.parametrize(
        ("text", "expected_base"),
        [
            ("SUBTOTAL: EUR 1409.40", 1409.40),
            ("BASE IMPONIBLE: 2.301,34", 2301.34),
            ("IMPORTE BASE: 500,00", 500.00),
            ("Base: 1.250,00 €", 1250.00),
            ("Importe base: 350.75", 350.75),
            ("BASE IMPONIBLE ... 10.000,50", 10000.50),
        ],
    )
    def test_base_variaciones(self, text: str, expected_base: float):
        val, conf = _base(text)
        assert val == expected_base
        assert conf > 0.0
        assert FORMAT_TESTS["AMOUNT_POSITIVE"](val)

    @pytest.mark.parametrize(
        ("text", "expected_total"),
        [
            ("TOTAL A PAGAR: EUR 1705.37", 1705.37),
            ("Total factura: 7.917,62 €", 7917.62),
            ("TOTAL: 1.210,00 €", 1210.00),
            ("TOTAL (IVA INCLUIDO): 1.210,00 €", 1210.00),
            ("IMPORTE TOTAL: EUR 2500,00", 2500.00),
            ("Total: 543,21", 543.21),
        ],
    )
    def test_total_variaciones(self, text: str, expected_total: float):
        val, conf = _total(text)
        assert val == expected_total
        assert conf > 0.0
        assert FORMAT_TESTS["AMOUNT_POSITIVE"](val)

    def test_subtotal_no_enmascara_total(self):
        documento = """
        FACTURA Nº F-2026/042
        SUBTOTAL: EUR 1409.40
        I.V.A. (21%): 295.97
        TOTAL A PAGAR: EUR 1705.37
        """
        base_val, base_conf = _base(documento)
        total_val, total_conf = _total(documento)

        assert base_val == 1409.40
        assert total_val == 1705.37
        assert base_conf > 0.0
        assert total_conf > 0.0


class TestAllExtractorsRegistry:
    def test_all_extractors_structure(self):
        registry = all_extractors()
        assert len(registry) == 8
        field_types = {field_type for field_type, _, _ in registry}
        assert field_types == {
            "nif",
            "iban",
            "total",
            "base",
            "iva_rate",
            "iva_amount",
            "fecha",
            "pedido",
        }
        for field_type, name, fn in registry:
            assert callable(fn)
            val, conf = fn("")
            assert isinstance(conf, float)
