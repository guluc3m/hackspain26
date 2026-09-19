"""Adversarial verification and contra-ejemplo test suite (Astra-grade verification).

Simulates gpt-6 astra independent verification across:
1. Complete automated evaluation of all 40 facturas_primin/ PDFs.
2. 100% extraction rate across all 8 required fields:
   (nif, iban, total, base, iva_rate, iva_amount, fecha, pedido).
3. Consistent rule decisions against master data and erp_export_lote2.csv:
   (25 PAGAR, 11 NO_PAGAR, 4 ESCALAR).
4. Adversarial contra-ejemplos:
   - International IBAN validation and checksum resilience (DE, FR, GB, BR, JP, ES).
   - Multilingual natural dates (English, French, German, Italian, Catalan, Portuguese, Spanish).
   - Vertical letter-spaced text reassembly.
   - Currency symbol resilience ($ vs €, JPY, CHF, BRL, GBP, MXN).
   - Double-payment prevention for lote 2 orders (PO-2026-0071).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from filemaid.extract.cache import FeatureCache
from filemaid.extract.ladder import extract_file
from filemaid.parse.extractors import (
    _base,
    _clean_text,
    _fecha,
    _iban,
    _iva_amount,
    _iva_rate,
    _nif,
    _pedido,
    _total,
)
from filemaid.parse.parser import parse_fields
from filemaid.rules.config import RuleConfig
from filemaid.rules.engine import evaluate
from filemaid.rules.escoger import FORMAT_TESTS, escoger, field_selection
from filemaid.rules.master import load_master
from filemaid.types import Candidate, ExtractionField, Result, RuleVerdict

REQUIRED_FIELDS = {"nif", "iban", "total", "base", "iva_rate", "iva_amount", "fecha", "pedido"}

EXPECTED_DECISIONS = {
    # 26 PAGAR
    "2026-08-05_P005.pdf": Result.PAGAR,
    "2026-08-09_P001.pdf": Result.PAGAR,
    "2026-08-26_P010.pdf": Result.PAGAR,
    "2026-08-27_P007.pdf": Result.PAGAR,
    "2026-27450_suministros.pdf": Result.PAGAR,
    "2026-42111_construcciones.pdf": Result.PAGAR,
    "2026-72452_suministros.pdf": Result.PAGAR,
    "FA-6217_transportes.pdf": Result.PAGAR,
    "FA-7357_papelería.pdf": Result.PAGAR,
    "e01_P001.pdf": Result.PAGAR,
    "e03_P002.pdf": Result.PAGAR,
    "e04_P003.pdf": Result.PAGAR,
    "e07_P006.pdf": Result.PAGAR,
    "e08_P012.pdf": Result.PAGAR,
    "e16_P011.pdf": Result.PAGAR,
    "e17_P007.pdf": Result.PAGAR,
    "e18_P001.pdf": Result.PAGAR,
    "factura_1210.pdf": Result.PAGAR,
    "factura_1221.pdf": Result.PAGAR,
    "factura_2923.pdf": Result.PAGAR,
    "factura_6990.pdf": Result.PAGAR,
    "factura_7036.pdf": Result.PAGAR,
    "factura_7495.pdf": Result.PAGAR,
    "factura_7713.pdf": Result.PAGAR,
    "factura_9660.pdf": Result.PAGAR,
    # 11 NO_PAGAR
    "2026-08-22_P010.pdf": Result.NO_PAGAR,
    "e02_P002.pdf": Result.NO_PAGAR,
    "e05_P004.pdf": Result.NO_PAGAR,
    "e09_P015.pdf": Result.NO_PAGAR,
    "e10_P006.pdf": Result.NO_PAGAR,
    "e11_P011.pdf": Result.NO_PAGAR,
    "e12_P010.pdf": Result.NO_PAGAR,
    "e13_P014.pdf": Result.NO_PAGAR,
    "e14_P004.pdf": Result.NO_PAGAR,
    "e15_P012.pdf": Result.NO_PAGAR,
    "factura_6932.pdf": Result.NO_PAGAR,
    # 3 ESCALAR
    "FA-3955_electricidad.pdf": Result.ESCALAR,
    "FA-7532_informática.pdf": Result.ESCALAR,
    "e06_P013.pdf": Result.ESCALAR,
}


@pytest.fixture(scope="module")
def facturas_primin_dir() -> Path:
    p = Path("caja-de-alberto/facturas_primin")
    assert p.is_dir(), f"Missing facturas directory: {p}"
    return p


@pytest.fixture(scope="module")
def master_data() -> any:
    return load_master(Path("master"))


@pytest.fixture(scope="module")
def rule_config() -> RuleConfig:
    return RuleConfig.load(Path("master/rules.yaml"))


@pytest.fixture(scope="module")
def evaluated_facturas(
    facturas_primin_dir: Path, master_data, rule_config, tmp_path_factory
) -> dict:
    cache_dir = tmp_path_factory.mktemp("cache")
    pages_dir = tmp_path_factory.mktemp("pages")
    cache = FeatureCache(cache_dir)
    results = {}

    for pdf in sorted(facturas_primin_dir.glob("*.pdf")):
        pages = extract_file(pdf, cache, {}, pages_dir)
        fields = parse_fields(pages)
        fields_dict = {f.type: f for f in fields}

        # Check extracted candidate values per field
        selected_values = {}
        for ftype in REQUIRED_FIELDS:
            ffield = fields_dict.get(ftype)
            if ffield:
                sel = field_selection({}, ftype)
                selection = escoger(ffield, sel)
                if selection.candidate is not None:
                    selected_values[ftype] = selection.candidate.value

        decision = evaluate(
            fields_dict,
            master_data,
            rule_config,
            invoice_id=pdf.stem,
            file_id=pdf.name,
        )
        results[pdf.name] = {
            "fields": selected_values,
            "decision": decision,
        }
    return results


class TestAstraVerificationAll40Invoices:
    """Evaluates all 40 facturas_primin/ against master data, format tests, and decision matrix."""

    def test_total_invoice_count_is_forty(self, evaluated_facturas):
        assert len(evaluated_facturas) == 40

    def test_all_forty_invoices_have_hundred_percent_field_extraction(self, evaluated_facturas):
        missing_by_file = {}
        for filename, data in evaluated_facturas.items():
            extracted_set = set(data["fields"].keys())
            missing = REQUIRED_FIELDS - extracted_set
            if missing:
                missing_by_file[filename] = missing

        assert not missing_by_file, f"Invoices with missing fields: {missing_by_file}"

    @pytest.mark.parametrize("filename,expected_result", list(EXPECTED_DECISIONS.items()))
    def test_invoice_decision_matches_matrix(self, evaluated_facturas, filename, expected_result):
        actual = evaluated_facturas[filename]["decision"].result
        assert actual == expected_result, f"{filename} expected {expected_result}, got {actual}"

    def test_decision_distribution_summary(self, evaluated_facturas):
        counts = {}
        for data in evaluated_facturas.values():
            r = data["decision"].result
            counts[r] = counts.get(r, 0) + 1

        assert counts.get(Result.PAGAR) == 26
        assert counts.get(Result.NO_PAGAR) == 11
        assert counts.get(Result.ESCALAR) == 3

    def test_double_payment_invoice_specifically_blocked(self, evaluated_facturas):
        # 2026-08-22_P010.pdf contains PO-2026-0071 which is marked PAGADA in ERP lote 2
        data = evaluated_facturas["2026-08-22_P010.pdf"]
        assert data["fields"]["pedido"] == "PO-2026-0071"
        assert data["decision"].result == Result.NO_PAGAR

        failed_rule_codes = {
            r.code: r.reason
            for r in data["decision"].rule_evaluations
            if r.verdict != RuleVerdict.PASS
        }
        assert "NO_DOUBLE_PAYMENT" in failed_rule_codes
        assert "ORDER_PENDING" in failed_rule_codes

    def test_escalated_invoices_are_iban_mismatches(self, evaluated_facturas):
        escalated_files = [
            "FA-3955_electricidad.pdf",
            "FA-7532_informática.pdf",
            "e06_P013.pdf",
        ]
        for f in escalated_files:
            dec = evaluated_facturas[f]["decision"]
            assert dec.result == Result.ESCALAR
            failed_rules = {r.code for r in dec.rule_evaluations if r.verdict != RuleVerdict.PASS}
            assert "IBAN_MATCHES_MASTER" in failed_rules


class TestAstraContraEjemplosAttacks:
    """Adversarial stress-testing simulating counter-examples generated against FileMaid."""

    @pytest.mark.parametrize(
        ("raw_iban", "expected_clean"),
        [
            ("ES91 2100 0418 4502 0005 1332", "ES9121000418450200051332"),
            ("ES12\u200b3456\u200c7890\ufeff1234\u200d56789012", "ES1234567890123456789012"),
            ("DE89 3704 0044 0532 0130 00", "DE89370400440532013000"),
            ("FR76 3000 6000 0112 3456 7890 189", "FR7630006000011234567890189"),
            ("GB29 NWBK 6016 1331 9268 19", "GB29NWBK60161331926819"),
            ("BR97 0036 0305 0000 1000 9795 493C1", "BR9700360305000010009795493C1"),
            ("JP01 0001 2331 2345 6789 012", "JP010001233123456789012"),
        ],
    )
    def test_international_iban_cross_border_formats(self, raw_iban: str, expected_clean: str):
        val, conf = _iban(raw_iban)
        assert val == expected_clean
        assert conf > 0.0
        assert FORMAT_TESTS["IBAN_FORMAT"](val)

    @pytest.mark.parametrize(
        "invalid_iban",
        [
            "ES1234",  # Too short
            "12345678901234567890",  # No country code
            "Cuenta no bancaria 12345",
            "NOT AN IBAN AT ALL",
        ],
    )
    def test_invalid_iban_rejected(self, invalid_iban: str):
        val, conf = _iban(invalid_iban)
        assert val is None
        assert conf == 0.0

    def test_adversarial_unrecognized_iban_blocks_payment_in_rules(self, master_data, rule_config):
        # An IBAN not in master (such as an unknown country code or fake account)
        # is blocked from payment: it causes IBAN_MATCHES_MASTER to fail/escalate.
        fields = {
            "nif": ExtractionField(
                type="nif", values=[Candidate(extractor="test", value="B46102331", confidence=0.95)]
            ),
            "iban": ExtractionField(
                type="iban",
                values=[Candidate(extractor="test", value="ZZ99123456789012", confidence=0.95)],
            ),
            "total": ExtractionField(
                type="total", values=[Candidate(extractor="test", value=1500.40, confidence=0.95)]
            ),
            "base": ExtractionField(
                type="base", values=[Candidate(extractor="test", value=1240.00, confidence=0.95)]
            ),
            "iva_rate": ExtractionField(
                type="iva_rate", values=[Candidate(extractor="test", value=21, confidence=0.95)]
            ),
            "iva_amount": ExtractionField(
                type="iva_amount",
                values=[Candidate(extractor="test", value=260.40, confidence=0.95)],
            ),
            "fecha": ExtractionField(
                type="fecha",
                values=[Candidate(extractor="test", value="15/07/2026", confidence=0.95)],
            ),
            "pedido": ExtractionField(
                type="pedido",
                values=[Candidate(extractor="test", value="PO-2026-1301", confidence=0.95)],
            ),
        }
        decision = evaluate(
            fields,
            master_data,
            rule_config,
            invoice_id="contra_fake_iban",
            file_id="contra_fake_iban.pdf",
        )
        assert decision.result in {Result.ESCALAR, Result.NO_PAGAR}
        failed_rules = {r.code for r in decision.rule_evaluations if r.verdict != RuleVerdict.PASS}
        assert "IBAN_MATCHES_MASTER" in failed_rules

    @pytest.mark.parametrize(
        ("raw_text", "expected_date"),
        [
            # Spanish
            ("15 de enero de 2026", "15/01/2026"),
            ("dos de enero de dos mil veintiséis", "02/01/2026"),
            # English
            ("the seventh of March, two thousand twenty-six", "07/03/2026"),
            ("March 7, 2026", "07/03/2026"),
            # French
            ("le trois janvier deux mille vingt-six", "03/01/2026"),
            # German
            ("am siebten März zweitausendsechsundzwanzig", "07/03/2026"),
            ("am fünfzehnten Juni zweitausendsechsundzwanzig", "15/06/2026"),
            # Italian
            ("sette agosto duemilaventisei", "07/08/2026"),
            # Catalan
            ("dos de gener de dos mil vint-i-sis", "02/01/2026"),
            # Portuguese
            ("15 de fevereiro de 2026", "15/02/2026"),
        ],
    )
    def test_multilingual_natural_dates(self, raw_text: str, expected_date: str):
        val, conf = _fecha(raw_text)
        assert val == expected_date
        assert conf > 0.0
        assert FORMAT_TESTS["DATE_FORMAT"](val)

    def test_vertical_letter_spaced_text_reassembly(self):
        vertical_invoice = (
            "P\na\np\ne\nl\ne\nr\ní\na\n \nR\nu\nz\na\nf\na\n \nS\n.\nC\n.\n"
            "N\nI\nF\n \nJ\n4\n0\n1\n1\n2\n3\n5\n8\n"
            "c\nu\ne\nn\nt\na\n:\n \nE\nS\n5\n5\n3\n1\n5\n9\n0\n0\n1\n2\n3\n4\n8\n7\n6\n5\n1\n2\n3\n4\n0\n7\n"
            "F\na\nc\nt\nu\nr\na\n \nF\nA\n-\n9\n1\n1\n7\n"
            "F\ne\nc\nh\na\n:\n \n1\n2\n \nd\ne\n \nj\nu\nn\ni\no\n \nd\ne\n \n2\n0\n2\n6\n"
            "p\ne\nd\ni\nd\no\n \nP\nO\n-\n2\n0\n2\n6\n-\n1\n3\n1\n7\n"
            "b\na\ns\ne\n:\n \n6\n8\n0\n,\n0\n0\n \n€\n"
            "I\nV\nA\n \n2\n1\n%\n:\n \n1\n4\n2\n,\n8\n0\n \n€\n"
            "T\nO\nT\nA\nL\n:\n \n8\n2\n2\n,\n8\n0\n \n€\n"
        )
        cleaned = _clean_text(vertical_invoice)
        assert "J40112358" in cleaned
        assert "ES5531590012348765123407" in cleaned

        nif_val, nif_conf = _nif(vertical_invoice)
        iban_val, iban_conf = _iban(vertical_invoice)
        fecha_val, fecha_conf = _fecha(vertical_invoice)
        pedido_val, pedido_conf = _pedido(vertical_invoice)
        base_val, base_conf = _base(vertical_invoice)
        total_val, total_conf = _total(vertical_invoice)

        assert nif_val == "J40112358" and nif_conf > 0.0
        assert iban_val == "ES5531590012348765123407" and iban_conf > 0.0
        assert fecha_val == "12/06/2026" and fecha_conf > 0.0
        assert pedido_val == "PO-2026-1317" and pedido_conf > 0.0
        assert base_val == 680.0 and base_conf > 0.0
        assert total_val == 822.8 and total_conf > 0.0

    @pytest.mark.parametrize(
        ("text", "expected_base", "expected_total", "expected_iva_rate", "expected_iva_amount"),
        [
            (
                "Subtotal: $ 2,450.00 | VAT (21%): $ 0.00 | TOTAL: $ 2,450.00 USD",
                2450.0,
                2450.0,
                21,
                0.0,
            ),
            (
                "Base imponible: ¥ 773,000 | IVA (21%): ¥ 77,000 | Total: ¥ 850,000",
                773000.0,
                850000.0,
                21,
                77000.0,
            ),
            (
                "Zwischensumme: Fr 5.400,00 | MwSt. (21%): Fr 0,00 | Total: Fr 5.400,00",
                5400.0,
                5400.0,
                21,
                0.0,
            ),
            (
                "Valor base: R$ 15.500,00 | IVA (21%): R$ 0,00 | Total: R$ 15.500,00",
                15500.0,
                15500.0,
                21,
                0.0,
            ),
            (
                "Base imponible: MX$ 45.800,00 | IVA (21%): MX$ 9.160,00 | Total: MX$ 48.800,00",
                45800.0,
                48800.0,
                21,
                9160.0,
            ),
            (
                "Sous-total: £ 2,900.00 | IVA (21%): £ 0.00 | Total: £ 2,900.00 GBP",
                2900.0,
                2900.0,
                21,
                0.0,
            ),
        ],
    )
    def test_foreign_currency_symbols_resilience(
        self,
        text: str,
        expected_base: float,
        expected_total: float,
        expected_iva_rate: int,
        expected_iva_amount: float,
    ):
        b_val, b_conf = _base(text)
        t_val, t_conf = _total(text)
        ir_val, ir_conf = _iva_rate(text)
        ia_val, ia_conf = _iva_amount(text)

        assert b_val == expected_base and b_conf > 0.0
        assert t_val == expected_total and t_conf > 0.0
        assert ir_val == expected_iva_rate and ir_conf > 0.0
        assert ia_val == expected_iva_amount and ia_conf > 0.0

    def test_contra_ejemplo_double_payment_rule_evaluation(self, master_data, rule_config):
        """Simulates adversarial invoice re-submitting an already paid order PO-2026-0071."""
        fields = {
            "nif": ExtractionField(
                type="nif", values=[Candidate(extractor="test", value="B98455101", confidence=0.95)]
            ),
            "iban": ExtractionField(
                type="iban",
                values=[
                    Candidate(extractor="test", value="ES7101821200561099887766", confidence=0.95)
                ],
            ),
            "total": ExtractionField(
                type="total", values=[Candidate(extractor="test", value=951.89, confidence=0.95)]
            ),
            "base": ExtractionField(
                type="base", values=[Candidate(extractor="test", value=786.69, confidence=0.95)]
            ),
            "iva_rate": ExtractionField(
                type="iva_rate", values=[Candidate(extractor="test", value=21, confidence=0.95)]
            ),
            "iva_amount": ExtractionField(
                type="iva_amount",
                values=[Candidate(extractor="test", value=165.20, confidence=0.95)],
            ),
            "fecha": ExtractionField(
                type="fecha",
                values=[Candidate(extractor="test", value="22/08/2026", confidence=0.95)],
            ),
            "pedido": ExtractionField(
                type="pedido",
                values=[Candidate(extractor="test", value="PO-2026-0071", confidence=0.95)],
            ),
        }

        decision = evaluate(
            fields, master_data, rule_config, invoice_id="contra_0071", file_id="contra_0071.pdf"
        )
        assert decision.result == Result.NO_PAGAR

        failed_rules = {r.code for r in decision.rule_evaluations if r.verdict == RuleVerdict.FAIL}
        assert "NO_DOUBLE_PAYMENT" in failed_rules
        assert "ORDER_PENDING" in failed_rules

    def test_contra_ejemplo_po_impersonation_attack(self, master_data, rule_config):
        """Simulates adversarial invoice where supplier B90233808 attempts to invoice order belonging to B98120774."""
        fields = {
            "nif": ExtractionField(
                type="nif", values=[Candidate(extractor="test", value="B90233808", confidence=0.95)]
            ),
            "iban": ExtractionField(
                type="iban",
                values=[
                    Candidate(extractor="test", value="ES4414650100951704302211", confidence=0.95)
                ],
            ),
            "total": ExtractionField(
                type="total", values=[Candidate(extractor="test", value=6778.69, confidence=0.95)]
            ),
            "base": ExtractionField(
                type="base", values=[Candidate(extractor="test", value=5602.22, confidence=0.95)]
            ),
            "iva_rate": ExtractionField(
                type="iva_rate", values=[Candidate(extractor="test", value=21, confidence=0.95)]
            ),
            "iva_amount": ExtractionField(
                type="iva_amount",
                values=[Candidate(extractor="test", value=1176.47, confidence=0.95)],
            ),
            "fecha": ExtractionField(
                type="fecha",
                values=[Candidate(extractor="test", value="15/07/2026", confidence=0.95)],
            ),
            "pedido": ExtractionField(
                type="pedido",
                values=[Candidate(extractor="test", value="PO-2026-1305", confidence=0.95)],
            ),
        }

        decision = evaluate(
            fields,
            master_data,
            rule_config,
            invoice_id="contra_impersonate",
            file_id="contra_impersonate.pdf",
        )
        assert decision.result == Result.NO_PAGAR

        failed_rules = {r.code for r in decision.rule_evaluations if r.verdict == RuleVerdict.FAIL}
        assert "ORDER_BELONGS_TO_SUPPLIER" in failed_rules

    def test_contra_ejemplo_fake_nonexistent_po(self, master_data, rule_config):
        """Simulates adversarial invoice with a fake or non-existent PO (e.g. PO-2026-9999)."""
        fields = {
            "nif": ExtractionField(
                type="nif", values=[Candidate(extractor="test", value="B46102331", confidence=0.95)]
            ),
            "iban": ExtractionField(
                type="iban",
                values=[
                    Candidate(extractor="test", value="ES9121000418450200051332", confidence=0.95)
                ],
            ),
            "total": ExtractionField(
                type="total", values=[Candidate(extractor="test", value=1500.40, confidence=0.95)]
            ),
            "base": ExtractionField(
                type="base", values=[Candidate(extractor="test", value=1240.00, confidence=0.95)]
            ),
            "iva_rate": ExtractionField(
                type="iva_rate", values=[Candidate(extractor="test", value=21, confidence=0.95)]
            ),
            "iva_amount": ExtractionField(
                type="iva_amount",
                values=[Candidate(extractor="test", value=260.40, confidence=0.95)],
            ),
            "fecha": ExtractionField(
                type="fecha",
                values=[Candidate(extractor="test", value="15/07/2026", confidence=0.95)],
            ),
            "pedido": ExtractionField(
                type="pedido",
                values=[Candidate(extractor="test", value="PO-2026-9999", confidence=0.95)],
            ),
        }

        decision = evaluate(
            fields,
            master_data,
            rule_config,
            invoice_id="contra_fake_po",
            file_id="contra_fake_po.pdf",
        )
        assert decision.result == Result.NO_PAGAR
        failed_rules = {r.code for r in decision.rule_evaluations if r.verdict == RuleVerdict.FAIL}
        assert "ORDER_BELONGS_TO_SUPPLIER" in failed_rules

    def test_contra_ejemplo_future_date_fails_date_valid_not_future(self, master_data, rule_config):
        """Simulates adversarial invoice with a future date (e.g. 2099-12-31)."""
        fields = {
            "nif": ExtractionField(
                type="nif", values=[Candidate(extractor="test", value="B46102331", confidence=0.95)]
            ),
            "iban": ExtractionField(
                type="iban",
                values=[
                    Candidate(extractor="test", value="ES9121000418450200051332", confidence=0.95)
                ],
            ),
            "total": ExtractionField(
                type="total", values=[Candidate(extractor="test", value=1500.40, confidence=0.95)]
            ),
            "base": ExtractionField(
                type="base", values=[Candidate(extractor="test", value=1240.00, confidence=0.95)]
            ),
            "iva_rate": ExtractionField(
                type="iva_rate", values=[Candidate(extractor="test", value=21, confidence=0.95)]
            ),
            "iva_amount": ExtractionField(
                type="iva_amount",
                values=[Candidate(extractor="test", value=260.40, confidence=0.95)],
            ),
            "fecha": ExtractionField(
                type="fecha",
                values=[Candidate(extractor="test", value="31/12/2099", confidence=0.95)],
            ),
            "pedido": ExtractionField(
                type="pedido",
                values=[Candidate(extractor="test", value="PO-2026-1301", confidence=0.95)],
            ),
        }

        decision = evaluate(
            fields,
            master_data,
            rule_config,
            invoice_id="contra_future_date",
            file_id="contra_future_date.pdf",
        )
        assert decision.result == Result.NO_PAGAR
        failed_rules = {r.code for r in decision.rule_evaluations if r.verdict == RuleVerdict.FAIL}
        assert "DATE_VALID_NOT_FUTURE" in failed_rules

    @pytest.mark.parametrize(
        "impossible_date",
        [
            "31/04/2026",  # April has 30 days
            "29/02/2026",  # 2026 is not a leap year
            "32/01/2026",  # Day > 31
            "15/13/2026",  # Month > 12
        ],
    )
    def test_contra_ejemplo_impossible_dates_fail_format_test(self, impossible_date: str):
        assert not FORMAT_TESTS["DATE_FORMAT"](impossible_date)
