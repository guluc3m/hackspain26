from __future__ import annotations

import base64
import csv
import io
import re
import zlib
from pathlib import Path

from filemaid.rules.config import RuleConfig
from filemaid.rules.engine import evaluate
from filemaid.rules.master import load_master
from filemaid.types import ExtractionField, Result, RuleVerdict

REPO_ROOT = Path(__file__).resolve().parent.parent
ERP_SCRIPT_PATH = REPO_ROOT / "caja-de-alberto" / "alberto_erp.py"
MASTER_DIR = REPO_ROOT / "master"


def _extract_embedded_erp_records() -> list[dict[str, str]]:
    """Decode base64 + zlib data block from caja-de-alberto/alberto_erp.py."""
    content = ERP_SCRIPT_PATH.read_text(encoding="utf-8")
    m = re.search(r"_DATOS_ERP\s*=\s*\((.*?)\n\)", content, re.DOTALL)
    assert m is not None, "Could not find _DATOS_ERP block in alberto_erp.py"
    raw_b64 = "".join(line.strip().strip('"') for line in m.group(1).splitlines() if line.strip())
    decompressed = zlib.decompress(base64.b64decode(raw_b64)).decode("utf-8")
    return list(csv.DictReader(io.StringIO(decompressed)))


def test_erp_submodule_decompression_and_columns():
    """Verify that _DATOS_ERP decompress properly and contain expected AS/400 columns."""
    records = _extract_embedded_erp_records()
    assert len(records) > 0
    expected_cols = {
        "asiento_id",
        "fecha_registro",
        "proveedor_id",
        "nif",
        "pedido",
        "importe_esperado",
        "estado",
    }
    assert expected_cols.issubset(records[0].keys())


def test_all_erp_entries_present_in_master():
    """Verify that every order in ERP exists in master/pedidos.csv with matching NIF and amount."""
    master = load_master(MASTER_DIR)
    erp_records = _extract_embedded_erp_records()

    for row in erp_records:
        num = row["pedido"].strip().upper()
        assert num in master.pedidos, f"Order {num} from ERP not found in master/pedidos.csv"
        order = master.pedidos[num]

        # Verify NIF matches if present in ERP
        erp_nif = row["nif"].strip().upper()
        if erp_nif:
            assert order.nif_proveedor == erp_nif, (
                f"NIF mismatch for {num}: master={order.nif_proveedor}, erp={erp_nif}"
            )

        # Verify amount matches within float rounding tolerance (1 cent)
        erp_importe = float(row["importe_esperado"])
        assert abs(order.importe - erp_importe) < 0.01, (
            f"Amount mismatch for {num}: master={order.importe}, erp={erp_importe}"
        )


def test_erp_pagada_orders_synchronized_and_prevent_double_payment():
    """Verify that orders marked PAGADA in ERP are marked pagado=True in master.

    Asserts that rule evaluation (NO_DOUBLE_PAYMENT & ORDER_PENDING) results in NO_PAGAR.
    """
    master = load_master(MASTER_DIR)
    erp_records = _extract_embedded_erp_records()
    rule_config = RuleConfig.load(MASTER_DIR / "rules.yaml")

    pagada_in_erp = [r for r in erp_records if r["estado"].strip().upper() == "PAGADA"]
    expected_pagada_ids = {
        "PO-2026-0471",
        "PO-2026-0472",
        "PO-2026-0473",
        "PO-2026-0474",
        "PO-2026-0475",
        "PO-2026-0476",
        "PO-2026-0703",
        "PO-2026-0803",
        "PO-2026-0814",
    }

    assert {r["pedido"] for r in pagada_in_erp} == expected_pagada_ids

    all_pagada_ids = set(expected_pagada_ids) | {"PO-2026-0071"}
    for num in all_pagada_ids:
        order = master.pedidos[num]
        assert order.pagado is True, f"Order {num} is PAGADA but pagado is False in master"
        assert order.estado == "PAGADA", (
            f"Order {num} is PAGADA but estado is {order.estado} in master"
        )

        # Mock an incoming invoice attempting to pay for this already paid order
        supplier = master.proveedores.get(order.nif_proveedor)
        nif_val = supplier.nif if supplier else order.nif_proveedor
        iban_val = supplier.iban if supplier else "ES9121000418450200051332"
        base_val = round(order.importe / 1.21, 2)
        iva_val = round(order.importe - base_val, 2)

        def _field(t: str, v: object) -> ExtractionField:
            f = ExtractionField(type=t)
            f.add("pypdf", v, 0.99)
            return f

        fields = {
            "nif": _field("nif", nif_val),
            "iban": _field("iban", iban_val),
            "pedido": _field("pedido", num),
            "total": _field("total", order.importe),
            "base": _field("base", base_val),
            "iva_amount": _field("iva_amount", iva_val),
            "iva_rate": _field("iva_rate", 21.0),
            "fecha": _field("fecha", "15/01/2026"),
        }

        decision = evaluate(fields, master, rule_config, f"inv-double-{num}", f"{num}.pdf")
        assert decision.result is Result.NO_PAGAR, f"Order {num} must be NO_PAGAR"
        ev_map = {e.code: e for e in decision.rule_evaluations}
        assert ev_map["NO_DOUBLE_PAYMENT"].verdict is RuleVerdict.FAIL
        assert ev_map["ORDER_PENDING"].verdict is RuleVerdict.FAIL


def test_adversarial_tampered_amount_and_unpaid_invariants():
    """Verify that unpaid orders in ERP remain PENDIENTE / pagado=False and pass NO_DOUBLE_PAYMENT."""
    master = load_master(MASTER_DIR)
    erp_records = _extract_embedded_erp_records()

    unpaid_in_erp = [
        r
        for r in erp_records
        if r["estado"].strip().upper() == "PENDIENTE" and r["pedido"] != "PO-2026-0071"
    ]
    assert len(unpaid_in_erp) == 506

    for r in unpaid_in_erp:
        num = r["pedido"]
        order = master.pedidos[num]
        assert order.pagado is False, (
            f"Order {num} is PENDIENTE in ERP but pagado is True in master"
        )
        assert order.estado == "PENDIENTE", f"Order {num} state mismatch: {order.estado}"

    # Adversarial test: tampered amount on an unpaid order must fail ORDER_BELONGS_TO_SUPPLIER
    rule_config = RuleConfig.load(MASTER_DIR / "rules.yaml")
    sample_unpaid = unpaid_in_erp[0]
    sample_num = sample_unpaid["pedido"]
    sample_order = master.pedidos[sample_num]
    supplier = master.proveedores.get(sample_order.nif_proveedor)
    nif_val = supplier.nif if supplier else sample_order.nif_proveedor
    iban_val = supplier.iban if supplier else "ES9121000418450200051332"

    def _field(t: str, v: object) -> ExtractionField:
        f = ExtractionField(type=t)
        f.add("pypdf", v, 0.99)
        return f

    # Tampered: invoice claims 999999.99 instead of expected amount
    tampered_fields = {
        "nif": _field("nif", nif_val),
        "iban": _field("iban", iban_val),
        "pedido": _field("pedido", sample_num),
        "total": _field("total", 999999.99),
        "base": _field("base", 826446.27),
        "iva_amount": _field("iva_amount", 173553.72),
        "iva_rate": _field("iva_rate", 21.0),
        "fecha": _field("fecha", "15/01/2026"),
    }
    tampered_dec = evaluate(tampered_fields, master, rule_config, "tampered-1", "f.pdf")
    assert tampered_dec.result is Result.NO_PAGAR
    ev_map = {e.code: e for e in tampered_dec.rule_evaluations}
    assert ev_map["ORDER_BELONGS_TO_SUPPLIER"].verdict is RuleVerdict.FAIL
