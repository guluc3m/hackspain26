from __future__ import annotations

import dataclasses

from albertitos.parse.normalizers import amounts_match, normalize_iban, normalize_nif, parse_amount
from albertitos.rules.engine import evaluate
from albertitos.types import ExtractionField, Result, RuleVerdict


def _field(tipo: str, valor, conf: float = 0.9, extractor: str = "test") -> ExtractionField:
    f = ExtractionField(type=tipo)
    f.add(extractor, valor, conf)
    return f


def _fields_ok(master) -> dict[str, ExtractionField]:
    return {
        "nif": _field("nif", "B12345678"),
        "iban": _field("iban", "ES9121000418450200051332"),
        "pedido": _field("pedido", "P-2026-001"),
        "total": _field("total", 121.00),
        "base": _field("base", 100.00),
        "iva_amount": _field("iva_amount", 21.00),
        "iva_rate": _field("iva_rate", 21),
        "fecha": _field("fecha", "01/01/2026"),
    }


def test_todo_pass_pagara(master, rule_config):
    d = evaluate(_fields_ok(master), master, rule_config, "inv-1", "f.pdf")
    assert d.result is Result.PAGAR
    assert all(e.verdict is RuleVerdict.PASS for e in d.rule_evaluations)


def test_nif_fuera_de_maestro_no_pagara(master, rule_config):
    fields = _fields_ok(master)
    fields["nif"] = _field("nif", "Z99999999")
    d = evaluate(fields, master, rule_config, "inv-2", "f.pdf")
    assert d.result is Result.NO_PAGAR
    fails = [e for e in d.rule_evaluations if e.verdict is RuleVerdict.FAIL]
    assert any(e.code == "NIF_IN_MASTER" for e in fails)


def test_duda_razonable_escala(master, rule_config):
    fields = _fields_ok(master)
    fields["fecha"] = _field("fecha", "31/02/2026", conf=0.9)
    d = evaluate(fields, master, rule_config, "inv-3", "f.pdf")
    assert d.result is Result.ESCALAR
    unknowns = [e for e in d.rule_evaluations if e.verdict is RuleVerdict.UNKNOWN]
    assert any(e.code == "DATE_VALID_NOT_FUTURE" for e in unknowns)


def test_confianza_baja_escala_no_interpreta_basura(master, rule_config):
    fields = _fields_ok(master)
    fields["nif"] = _field("nif", "B12345678", conf=0.3)
    d = evaluate(fields, master, rule_config, "inv-4", "f.pdf")
    assert d.result is Result.ESCALAR


def test_determinismo_byte_a_byte(master, rule_config):
    a = evaluate(_fields_ok(master), master, rule_config, "inv-5", "f.pdf")
    b = evaluate(_fields_ok(master), master, rule_config, "inv-5", "f.pdf")
    assert dataclasses.asdict(a) == dataclasses.asdict(b)


def test_orden_de_reglas_estable(master, rule_config):
    a = [e.code for e in evaluate(_fields_ok(master), master, rule_config, "inv-6", "f.pdf").rule_evaluations]
    b = [e.code for e in evaluate(_fields_ok(master), master, rule_config, "inv-6", "f.pdf").rule_evaluations]
    assert a == b == sorted(a)


def test_snapshot_incluye_versiones(master, rule_config):
    d = evaluate(_fields_ok(master), master, rule_config, "inv-7", "f.pdf", extractor_versions={"pypdf": "1"})
    assert d.config_snapshot.extractor_versions == {"pypdf": "1"}
    assert d.config_snapshot.master_sha256 == master.sha256


def test_pedido_duplicado_no_pagara(master, rule_config):
    master.pedidos["P-2026-001"].pagado = True
    d = evaluate(_fields_ok(master), master, rule_config, "inv-8", "f.pdf")
    assert d.result is Result.NO_PAGAR
    assert any(
        e.code == "NO_DOUBLE_PAYMENT" and e.verdict is RuleVerdict.FAIL
        for e in d.rule_evaluations
    )


def test_normalizadores():
    assert parse_amount("1.234,56 €") == 1234.56
    assert parse_amount("1,234.56") == 1234.56
    assert parse_amount("121,00") == 121.00
    assert normalize_nif(" b-12345678 ") == "B12345678"
    assert normalize_iban("ES91 2100 0418 4502 0005 1332") == "ES9121000418450200051332"
    assert amounts_match(100.001, 100.0, 0.01)
    assert not amounts_match(100.02, 100.0, 0.01)
