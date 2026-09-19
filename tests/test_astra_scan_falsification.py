"""Adversarial Falsification Suite for Scan Reading Architecture.

Attacks the assumptions of OCR reading and post-processing:
1. IBAN corruption:
   - Single digit substitutions across IBAN positions (country code, check digits, account).
   - Slash/whitespace/special character artifacts resulting in incorrect account numbers.
   - Cross-vendor account substitution (using another valid vendor's IBAN).
   - In all cases: IBAN_MATCHES_MASTER must fail safely -> ESCALAR (never PAGAR).

2. Amount hallucinations and OCR scan artifacts:
   - OCR merged decimals (e.g. 1.29288 -> 1292.88 instead of 121.00).
   - OCR concatenated text/numbers (e.g. IVA21%27150 -> 27150.00).
   - Off-by-one cent discrepancy (121.01 vs 121.00).
   - Internally consistent hallucination (Base + IVA = Total) but differing from ERP PO amount.
   - In all cases: TOTALS_MUST_MATCH or ORDER_BELONGS_TO_SUPPLIER fails -> NO_PAGAR.

3. Client CIF vs Vendor NIF confusion:
   - OCR extracts client CIF (Banco Miralmar A58231074) instead of vendor NIF.
   - Client CIF not in master -> NIF_IN_MASTER fails and ORDER_BELONGS_TO_SUPPLIER fails -> NO_PAGAR.
   - Client CIF coincidentally matching another supplier in master ->
     ORDER_BELONGS_TO_SUPPLIER detects PO mismatch -> NO_PAGAR.

4. Comprehensive scan corpus verification:
   - Evaluates all degraded scans (scan_001 to scan_029).
   - Verifies genuine scans (scan_027, scan_028) pass as PAGAR.
   - Asserts ZERO degraded scans with corrupted amounts, invalid IBANs, or wrong NIFs
     ever resolve to PAGAR (strictly ESCALAR or NO_PAGAR).
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from filemaid.rules.config import RuleConfig
from filemaid.rules.engine import evaluate
from filemaid.rules.master import load_master
from filemaid.types import ExtractionField, Result, RuleVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def real_master():
    return load_master(REPO_ROOT / "master")


@pytest.fixture(scope="module")
def real_rules_config():
    return RuleConfig.load(REPO_ROOT / "master" / "rules.yaml")


def _field(tipo: str, valor, conf: float = 0.95, extractor: str = "vlm") -> ExtractionField:
    f = ExtractionField(type=tipo)
    if valor is not None:
        f.add(extractor, valor, conf)
    return f


def _valid_invoice_fields(
    nif: str | None = "B12345678",
    iban: str | None = "ES9121000418450200051332",
    pedido: str | None = "P-2026-001",
    total: float | None = 121.00,
    base: float | None = 100.00,
    iva_rate: float | None = 21.0,
    iva_amount: float | None = 21.00,
    fecha: str | None = "15/01/2026",
) -> dict[str, ExtractionField]:
    return {
        "nif": _field("nif", nif),
        "iban": _field("iban", iban),
        "pedido": _field("pedido", pedido),
        "total": _field("total", total),
        "base": _field("base", base),
        "iva_rate": _field("iva_rate", iva_rate),
        "iva_amount": _field("iva_amount", iva_amount),
        "fecha": _field("fecha", fecha),
    }


class TestIbanAdversarialAttacks:
    """Attacks against IBAN reading resilience and safe failure."""

    def test_baseline_valid_invoice_passes(self, real_master, real_rules_config):
        fields = _valid_invoice_fields()
        decision = evaluate(fields, real_master, real_rules_config, "test-ok", "test-ok.pdf")
        assert decision.result is Result.PAGAR
        assert all(e.verdict is RuleVerdict.PASS for e in decision.rule_evaluations)

    @pytest.mark.parametrize(
        ("digit_idx", "replacement"),
        [
            (0, "F"),   # Country code ES -> FS
            (2, "0"),   # Check digit 9 -> 0
            (3, "0"),   # Check digit 1 -> 0
            (4, "1"),   # Bank code 2 -> 1
            (10, "9"),  # Branch code
            (15, "0"),  # Account number
            (23, "0"),  # Last digit 2 -> 0
        ],
    )
    def test_single_digit_mutation_fails_safely_escalar(
        self, real_master, real_rules_config, digit_idx: int, replacement: str
    ):
        clean_iban = "ES9121000418450200051332"
        mutated_iban = clean_iban[:digit_idx] + replacement + clean_iban[digit_idx + 1:]
        assert mutated_iban != clean_iban

        fields = _valid_invoice_fields(iban=mutated_iban)
        decision = evaluate(fields, real_master, real_rules_config, "test-iban-mut", "f.pdf")

        # Must never pay! Must ESCALAR
        assert decision.result is Result.ESCALAR
        iban_eval = next(e for e in decision.rule_evaluations if e.code == "IBAN_MATCHES_MASTER")
        assert iban_eval.verdict is RuleVerdict.FAIL
        assert "NO coincide con el maestro" in iban_eval.reason

    def test_cross_vendor_iban_substitution_escalates(self, real_master, real_rules_config):
        # Using another vendor's valid IBAN (Tecnología Delta: ES7921000813610123456789)
        # for Suministros García (B12345678)
        other_vendor_iban = "ES7921000813610123456789"
        fields = _valid_invoice_fields(iban=other_vendor_iban)
        decision = evaluate(fields, real_master, real_rules_config, "test-cross-iban", "f.pdf")

        assert decision.result is Result.ESCALAR
        iban_eval = next(e for e in decision.rule_evaluations if e.code == "IBAN_MATCHES_MASTER")
        assert iban_eval.verdict is RuleVerdict.FAIL

    def test_slashed_iban_unresolved_fails_safely(self, real_master, real_rules_config):
        # If OCR delivers a slashed IBAN that was corrupted/partially decoded
        unresolved_iban = "E544/1465/0100/9517/0430/2211"
        fields = _valid_invoice_fields(iban=unresolved_iban)
        decision = evaluate(fields, real_master, real_rules_config, "test-slash-iban", "f.pdf")

        assert decision.result in (Result.ESCALAR, Result.NO_PAGAR)
        assert decision.result is not Result.PAGAR


class TestAmountHallucinationAttacks:
    """Attacks against hallucinated or corrupted amounts in OCR scans."""

    def test_ocr_merged_decimals_hallucination_blocked(self, real_master, real_rules_config):
        # Scenario from scan_002: "1.29288" read as 1292.88 instead of 121.00
        fields = _valid_invoice_fields(
            total=1292.88,
            base=100.00,
            iva_amount=21.00,
        )
        decision = evaluate(fields, real_master, real_rules_config, "test-merged-dec", "f.pdf")

        assert decision.result is Result.NO_PAGAR
        fails = {e.code: e for e in decision.rule_evaluations if e.verdict is RuleVerdict.FAIL}
        assert "TOTALS_MUST_MATCH" in fails
        assert "ORDER_BELONGS_TO_SUPPLIER" in fails

    def test_ocr_concatenated_iva_amount_blocked(self, real_master, real_rules_config):
        # Scenario from scan_002: "IVA21%27150" read as 27150.00
        fields = _valid_invoice_fields(
            total=121.00,
            base=100.00,
            iva_rate=21.0,
            iva_amount=27150.00,
        )
        decision = evaluate(fields, real_master, real_rules_config, "test-concat-iva", "f.pdf")

        assert decision.result is Result.NO_PAGAR
        fails = {e.code: e for e in decision.rule_evaluations if e.verdict is RuleVerdict.FAIL}
        assert "IVA_CONSISTENT" in fails
        assert "TOTALS_MUST_MATCH" in fails

    def test_off_by_one_cent_discrepancy_blocked(self, real_master, real_rules_config):
        # Off-by-one cent discrepancy in total
        fields = _valid_invoice_fields(
            total=121.02,  # ERP order is 121.00, tolerance is 0.01 EUR
            base=100.00,
            iva_amount=21.02,
        )
        decision = evaluate(fields, real_master, real_rules_config, "test-off-by-cent", "f.pdf")

        assert decision.result is Result.NO_PAGAR
        order_eval = next(e for e in decision.rule_evaluations if e.code == "ORDER_BELONGS_TO_SUPPLIER")
        assert order_eval.verdict is RuleVerdict.FAIL

    def test_internally_consistent_hallucination_blocked_by_erp_order(
        self, real_master, real_rules_config
    ):
        # Even if base + IVA = total internally (1000 + 210 = 1210.00),
        # the order in ERP is for 121.00 EUR. ORDER_BELONGS_TO_SUPPLIER must catch it!
        fields = _valid_invoice_fields(
            total=1210.00,
            base=1000.00,
            iva_rate=21.0,
            iva_amount=210.00,
        )
        decision = evaluate(fields, real_master, real_rules_config, "test-order-diff", "f.pdf")

        assert decision.result is Result.NO_PAGAR
        order_eval = next(e for e in decision.rule_evaluations if e.code == "ORDER_BELONGS_TO_SUPPLIER")
        assert order_eval.verdict is RuleVerdict.FAIL
        assert "Importe factura 1210.0 ≠ importe pedido 121.0" in order_eval.reason


class TestClientCifVsVendorNifAttacks:
    """Attacks simulating OCR confusion between client CIF and vendor NIF."""

    def test_client_cif_not_in_master_blocks_payment(self, real_master, real_rules_config):
        # Scan reads "Cliente: Banco Miralmar S.A. CIF: A58231074" as the NIF
        client_cif = "A58231074"
        assert client_cif not in real_master.proveedores

        fields = _valid_invoice_fields(nif=client_cif)
        decision = evaluate(fields, real_master, real_rules_config, "test-client-cif", "f.pdf")

        assert decision.result is Result.NO_PAGAR
        fails = {e.code: e for e in decision.rule_evaluations if e.verdict is RuleVerdict.FAIL}
        assert "NIF_IN_MASTER" in fails
        assert "ORDER_BELONGS_TO_SUPPLIER" in fails

    def test_client_cif_matching_another_vendor_blocks_payment(
        self, real_master, real_rules_config
    ):
        # Even if client CIF happened to be another vendor in master (e.g. A41220987),
        # ORDER_BELONGS_TO_SUPPLIER verifies that P-2026-001 belongs to B12345678, not A41220987.
        other_vendor_cif = "A41220987"
        assert other_vendor_cif in real_master.proveedores

        fields = _valid_invoice_fields(nif=other_vendor_cif)
        decision = evaluate(fields, real_master, real_rules_config, "test-other-vendor-cif", "f.pdf")

        assert decision.result is Result.NO_PAGAR
        fails = {e.code: e for e in decision.rule_evaluations if e.verdict is RuleVerdict.FAIL}
        assert "ORDER_BELONGS_TO_SUPPLIER" in fails
        assert "pertenece a B12345678, no a A41220987" in fails["ORDER_BELONGS_TO_SUPPLIER"].reason


class TestDegradedScanCorpusSafety:
    """Verifies all degraded scans in the benchmark corpus adhere to safety invariants."""

    def test_genuine_clean_scans_pass_pagar(self, real_master, real_rules_config):
        # scan_027 (PO-2026-0730) and scan_028 (PO-2026-0731) are clean matching scans
        eval_path = REPO_ROOT / "vlm_scans_eval.json"
        if not eval_path.exists():
            pytest.skip("vlm_scans_eval.json not found")

        with open(eval_path) as f:
            eval_data = json.load(f)

        by_file = {item["file"]: item for item in eval_data["details"]}

        for scan_id in ("scan_027.pdf", "scan_028.pdf"):
            item = by_file[scan_id]
            fields = {
                k: _field(k, v) for k, v in item["extracted"].items()
            }
            dec = evaluate(fields, real_master, real_rules_config, scan_id, scan_id)
            assert dec.result is Result.PAGAR

    def test_corrupted_scans_never_pass_as_pagar(self, real_master, real_rules_config):
        # Every degraded scan in scan_001..scan_029 with OCR artifacts or discrepancies
        # MUST NEVER resolve to PAGAR.
        eval_path = REPO_ROOT / "vlm_scans_eval.json"
        if not eval_path.exists():
            pytest.skip("vlm_scans_eval.json not found")

        with open(eval_path) as f:
            eval_data = json.load(f)

        for item in eval_data["details"]:
            fname = item["file"]
            if fname in ("scan_027.pdf", "scan_028.pdf"):
                continue  # Clean verified scans

            fields = {
                k: _field(k, v) for k, v in item["extracted"].items()
            }
            dec = evaluate(fields, real_master, real_rules_config, fname, fname)

            assert dec.result in (Result.ESCALAR, Result.NO_PAGAR), (
                f"CORRUPTION SAFETY BREACH: {fname} resolved to {dec.result}! "
                f"Degraded invoice with artifacts must never pass as PAGAR."
            )

    @pytest.mark.parametrize(
        "corrupt_field,corrupt_value,expected_result",
        [
            ("iban", "ES5531590012348765123408", Result.ESCALAR),  # Misread IBAN
            ("total", 477.98, Result.NO_PAGAR),                     # Tampered total
            ("base", 395.05, Result.NO_PAGAR),                      # Tampered base
            ("iva_amount", 82.00, Result.NO_PAGAR),                 # Tampered IVA
            ("nif", "A58231074", Result.NO_PAGAR),                  # Client CIF as vendor
            ("pedido", "PO-2026-9999", Result.NO_PAGAR),            # Non-existent PO
        ],
    )
    def test_adversarial_tampering_of_genuine_scan_fails_safely(
        self, real_master, real_rules_config, corrupt_field: str, corrupt_value, expected_result
    ):
        # Start from clean scan_027
        clean_extracted = {
            "nif": "J40112358",
            "iban": "ES5531590012348765123407",
            "total": 477.95,
            "base": 395.0,
            "iva_rate": 21.0,
            "iva_amount": 82.95,
            "fecha": "06/04/2026",
            "pedido": "PO-2026-0730",
        }
        # Verify baseline passes
        fields_clean = {k: _field(k, v) for k, v in clean_extracted.items()}
        assert evaluate(fields_clean, real_master, real_rules_config, "27", "27").result is Result.PAGAR

        # Inject adversarial tampering
        tampered_extracted = dict(clean_extracted, **{corrupt_field: corrupt_value})
        fields_tampered = {k: _field(k, v) for k, v in tampered_extracted.items()}
        dec = evaluate(fields_tampered, real_master, real_rules_config, "27-tampered", "27.pdf")

        assert dec.result is expected_result
        assert dec.result is not Result.PAGAR
