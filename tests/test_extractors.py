from __future__ import annotations

import pytest

from filemaid.parse.extractors import (
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
from filemaid.rules.escoger import FORMAT_TESTS


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
            ("dos de enero de dos mil veintiséis", "02/01/2026"),
            ("the seventh of March, two thousand twenty-six", "07/03/2026"),
            ("03 Feb 2026", "03/02/2026"),
            ("March 7, 2026", "07/03/2026"),
            ("le trois janvier deux mille vingt-six", "03/01/2026"),
            ("am siebten März zweitausendsechsundzwanzig", "07/03/2026"),
            ("am fünfzehnten Juni zweitausendsechsundzwanzig", "15/06/2026"),
            ("sette agosto duemilaventisei", "07/08/2026"),
            ("dos de gener de dos mil vint-i-sis", "02/01/2026"),
            ("15 de fevereiro de 2026", "15/02/2026"),
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

    def test_fecha_placeholder_busca_en_documento(self):
        raw = (
            "FACTURA Nº: FA-9116\n"
            "Fecha de emisión: __________________________\n"
            "Ref. Pedido: PO-2026-1316\n"
            "Base imponible: 520,00 €\n"
            "15 de marzo de 2026\n"
        )
        val, conf = _fecha(raw)
        assert val == "15/03/2026"
        assert conf > 0.0

    def test_vertical_text_clean_and_date(self):
        raw = "F\ne\nc\nh\na\n:\n1\n2\nd\ne\nj\nu\nn\ni\no\nd\ne\n2\n0\n2\n6\n"
        val, conf = _fecha(raw)
        assert val == "12/06/2026"
        assert conf > 0.0


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
            ("TVA (21%): € 327,60", 21, 327.60),
            ("MwSt. (21%): € 655,20", 21, 655.20),
            ("VAT (21%): $ 0.00", 21, 0.0),
            ("IVA (21%): ¥ 77,000", 21, 77000.0),
            ("IVA (21%): R$ 0,00", 21, 0.0),
            ("IVA (21%): MX$ 9.160,00", 21, 9160.0),
            ("IVA (21%): Fr 0,00", 21, 0.0),
            ("IVA (21%): £ 0,00", 21, 0.0),
            ("MwSt. (21%): Fr 0,00", 21, 0.0),
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

    @pytest.mark.parametrize(
        ("text", "expected_iban"),
        [
            ("IBAN: ES18 0081 5290 0700 0123 4567", "ES1800815290070001234567"),
            ("IBAN: DE89 3704 0044 0532 0130 00", "DE89370400440532013000"),
            ("IBAN: FR76 3000 6000 0112 3456 7890 189", "FR7630006000011234567890189"),
            ("IBAN: GB29 NWBK 6016 1331 9268 19", "GB29NWBK60161331926819"),
            ("IBAN: BR97 0036 0305 0000 1000 9795 493C1", "BR9700360305000010009795493C1"),
            ("IBAN: JP01 0001 2331 2345 6789 012", "JP010001233123456789012"),
        ],
    )
    def test_iban_internacional(self, text: str, expected_iban: str):
        val, conf = _iban(text)
        assert val == expected_iban
        assert conf > 0.0
        assert FORMAT_TESTS["IBAN_FORMAT"](val)


class TestNifExtractor:
    @pytest.mark.parametrize(
        ("text", "expected_nif"),
        [
            ("NIF: B46102331", "B46102331"),
            ("CIF: A41220987", "A41220987"),
            ("NIF J40112358", "J40112358"),
            ("USt-ID: DE812345678", "DE812345678"),
            ("N° TVA: FR40303265045", "FR40303265045"),
            ("NIF: 12.345.678/0001-95", "12.345.678/0001-95"),
            ("NIF: 5010401075570", "5010401075570"),
            ("Tax ID: A41220987", "A41220987"),
            ("P. IVA: A46990201", "A46990201"),
        ],
    )
    def test_nif_internacional(self, text: str, expected_nif: str):
        val, conf = _nif(text)
        assert val == expected_nif
        assert conf > 0.0
        assert FORMAT_TESTS["NIF_FORMAT"](val)

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
            ("Base imponible: € 1.240,00", 1240.00),
            ("Subtotal: $ 2,450.00", 2450.00),
            ("Base imposable: € 1.180,00", 1180.00),
            ("Valor base: € 920,00", 920.00),
            ("Sous-total: € 1.560,00", 1560.00),
            ("Imponibile: € 2.340,00", 2340.00),
            ("Zwischensumme: € 3.120,00", 3120.00),
            ("Base imponible: ¥ 773,000", 773000.0),
            ("Valor base: R$ 15.500,00", 15500.00),
            ("Base imponible: MX$ 45.800,00", 45800.00),
            ("Zwischensumme: Fr 5.400,00", 5400.00),
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
            ("TOTAL: € 1.500,40 EUR", 1500.40),
            ("TOTAL: $ 2,450.00 USD", 2450.00),
            ("TOTALE: € 2.831,40 EUR", 2831.40),
            ("GESAMT: € 3.775,20 EUR", 3775.20),
            ("TOTAL: ¥ 850,000 JPY", 850000.0),
            ("TOTAL: Fr 4.200,00 CHF", 4200.00),
            ("TOTAL: R$ 15.500,00 BRL", 15500.00),
            ("TOTAL: MX$ 48.800,00 MXN", 48800.00),
            ("GESAMT: Fr 5.400,00 CHF", 5400.00),
            ("TOTAL: £ 2.900,00 GBP", 2900.00),
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
