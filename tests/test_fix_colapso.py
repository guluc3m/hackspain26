"""T18 · Fix del colapso de candidatos en el motor (ADR-06).

Semántica exacta (ticket T18): las reglas que comparan un campo contra el
maestro evalúan TODOS los candidatos del campo:
- exactamente uno matchea ⇒ PASS citando ESE candidato (provenance);
- varios matchean ⇒ PASS con nota de ambigüedad (concuerdan entre sí);
- ninguno ⇒ FAIL (los genuinos no cambian);
- PROHIBIDO que un PASS previo pase a FAIL.
"""

from __future__ import annotations

from albertitos.parse.normalizers import normalize_iban
from albertitos.parse.parser import field_by_type, parse_invoice
from albertitos.rules import BatchContext, decide, load_config, load_master
from albertitos.types import Candidate, ExtractionFeature, ExtractionField
from conftest import fixture_path

FECHA_REF = "2026-09-19"
RULES_YAML = "src/albertitos/rules/regla_v3.yaml"

# texto real de la trampa del T17 (2026-01-26_P007.pdf): Subtotal + TOTAL A PAGAR
TEXTO_SUBTOTAL_TOTAL = """PAPELERÍA RUZAFA S.C.
NIF: J40112358   |   Valencia
IBAN: ES55 3159 0012 3487 6512 3407
Invoice # FA-1480
Fecha factura: 26/01/2026    PO: PO-2026-0222
Bill to: Banco Miralmar S.A. (CIF: A58231074)
- Horas de soporte (1 ud): EUR 930.20
- Servicio de limpieza (1 ud): EUR 479.20
Subtotal: EUR 1409.40
IVA (21%): EUR 295.97
TOTAL A PAGAR: EUR 1705.37
Documento generado por el sistema de facturacion del proveedor.
"""


def _field(tipo: str, valores: list, extractor: str = "regex", conf: float = 0.9):
    return ExtractionField(
        type=tipo,
        timestamp=0.0,
        values=[Candidate(extractor, v, conf, f"{tipo}-ref-{i}") for i, v in enumerate(valores)],
    )


def _cfg():
    return load_config(RULES_YAML, fecha_referencia=FECHA_REF)


def _master():
    return load_master(fixture_path("maestro_fixture.xlsx"),
                       hojas_ignoradas=_cfg().hojas_ignoradas)


def _decide_fields(fields, *, pedido="PO-2026-0222"):
    d = decide(
        fields, (), _master(), _cfg(),
        BatchContext(facturas_vistas={}, pedidos_pagados=frozenset()),
        invoice_id="00000000-0000-0000-0000-000000000099",
        file_id="f.pdf",
    )
    return d, None


def _pedido_cualquiera(master) -> tuple[str, float]:
    """Primer pedido real del maestro y su importe (determinista)."""
    pid = min(master.pedidos)
    return pid, master.pedidos[pid].importe


def _verdict(d, code):
    for v in d.rule_verdicts:
        if v.code == code:
            return v
    raise AssertionError(f"sin veredicto {code}")


class TestOrderAmountEvaluaTodos:
    def test_subtotal_y_total_total_matchea_pass_con_provenance(self):
        """Candidatos Subtotal + TOTAL donde TOTAL matchea el maestro ⇒ PASS
        citando ESE candidato (provenance extractor+value+feature_ref)."""
        master = _master()
        pedido_id, imp = _pedido_cualquiera(master)
        fields = [_field("pedido", [pedido_id]),
                  _field("total", [round(imp / 1.21, 2), imp])]
        d, _ = _decide_fields(fields)
        v = _verdict(d, "ORDER_AMOUNT_MATCHES")
        assert v.outcome == "PASS"
        c = v.consumed
        assert c["candidatos_match"] == 1
        assert c["elegido"]["value"] == imp
        assert c["elegido"]["extractor"]
        assert c["elegido"]["feature_ref"] == "total-ref-1"

    def test_ningun_candidato_matchea_fail(self):
        master = _master()
        pedido_id, imp = _pedido_cualquiera(master)
        fields = [_field("pedido", [pedido_id]),
                  _field("total", [imp / 1.21, imp + 100.0])]
        d, _ = _decide_fields(fields)
        assert _verdict(d, "ORDER_AMOUNT_MATCHES").outcome == "FAIL"

    def test_dos_candidatos_matchean_pass_con_nota_ambiguedad(self):
        master = _master()
        pedido_id, imp = _pedido_cualquiera(master)
        fields = [_field("pedido", [pedido_id]),
                  _field("total", [imp, imp + 0.01])]  # ambos dentro de 0,01
        d, _ = _decide_fields(fields)
        v = _verdict(d, "ORDER_AMOUNT_MATCHES")
        assert v.outcome == "PASS"
        assert v.consumed["candidatos_match"] == 2
        assert v.consumed["ambiguo"] is True
        assert "concuerdan" in v.reason.lower()
        assert v.consumed["elegido"]["value"] == imp


class TestTotalsEvaluaaTodos:
    def test_totals_con_candidato_subtotal_y_total(self):
        fields = [
            _field("base", [1409.4]),
            _field("iva_amount", [295.97]),
            _field("total", [1409.4, 1705.37]),
        ]
        d, _ = _decide_fields(fields)
        v = _verdict(d, "TOTALS_MUST_MATCH")
        assert v.outcome == "PASS"
        assert v.consumed["elegido"]["value"] == 1705.37

    def test_totals_ninguno_cuadra_fail(self):
        fields = [
            _field("base", [1409.4]),
            _field("iva_amount", [295.97]),
            _field("total", [1409.4]),
        ]
        d, _ = _decide_fields(fields)
        assert _verdict(d, "TOTALS_MUST_MATCH").outcome == "FAIL"


class TestIvaConsistenteEvaluaTodos:
    def test_iva_segundo_candidato_pass(self):
        fields = [
            _field("base", [1409.4]),
            _field("iva_pct", [21]),
            _field("iva_amount", [300.0, 295.97]),
        ]
        d, _ = _decide_fields(fields)
        v = _verdict(d, "IVA_CONSISTENT")
        assert v.outcome == "PASS"
        assert v.consumed["elegido"]["value"] == 295.97


class TestIbanEvaluaaTodos:
    def test_iban_segundo_candidato_pass(self):
        master = _master()
        # NIF de un proveedor cuyo IBAN sea distinto de `otro` (sin empate benigno):
        # el 2º candidato es el correcto ⇒ se elige por provenance con su feature_ref
        nif = next(
            n for n, p in master.proveedores_por_nif.items()
            if p.iban and normalize_iban(p.iban) != normalize_iban("ES21 0049 1500 0512 3456 7890")
        )
        iban_maestro = master.proveedores_por_nif[nif].iban
        otro = "ES21 0049 1500 0512 3456 7890"
        fields = [_field("nif", [nif]), _field("iban", [otro, iban_maestro])]
        d, _ = _decide_fields(fields)
        v = _verdict(d, "IBAN_MATCHES_MASTER")
        assert v.outcome == "PASS"
        assert normalize_iban(str(v.consumed["elegido"]["value"])) == normalize_iban(iban_maestro)
        assert v.consumed["elegido"]["feature_ref"] == "iban-ref-1"


class TestNoRegresion:
    def test_pass_previo_no_se_vuelve_fail(self):
        """PROHIBIDO: un PASS previo convertirse en FAIL. Si el candidato
        elegido antes matcheaba, sigue matcheando (se evalúan todos)."""
        master = _master()
        pedido_id, imp = _pedido_cualquiera(master)
        fields = [_field("pedido", [pedido_id]), _field("total", [imp])]
        d, _ = _decide_fields(fields)
        assert _verdict(d, "ORDER_AMOUNT_MATCHES").outcome == "PASS"


class TestParserReal:
    def test_parser_emite_ambos_candidatos_total(self):
        """El caso real del T17: Subtotal y TOTAL A PAGAR son 2 candidatos."""
        feat = [ExtractionFeature(type="pdf_text", extraction_method="pypdf",
                                  timestamp=0.0, data=TEXTO_SUBTOTAL_TOTAL, page=1)]
        fields = parse_invoice(feat)
        total = field_by_type(fields, "total")
        vals = [c.value for c in total.values]
        assert 1409.4 in vals and 1705.37 in vals
