"""Tests del motor de reglas v3 (T3) — trampas de archivos-limpios incluidas."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import yaml

from albertitos.parse.parser import field_by_type, parse_invoice
from albertitos.rules import BatchContext, decide, load_config, load_master
from albertitos.rules.engine import RULES
from albertitos.types import Candidate, ExtractionFeature, ExtractionField
from conftest import fixture_path

FECHA_REF = "2026-09-19"
RULES_YAML = Path("src/albertitos/rules/regla_v3.yaml")
MASTER_XLSX = fixture_path("maestro_fixture.xlsx")

IBAN_P002 = "ES76 2100 0813 6101 2345 6789"
IBAN_P009 = "ES82 0128 0011 2301 0004 4571"


def _config():
    return load_config(RULES_YAML, fecha_referencia=FECHA_REF)


def _master():
    return load_master(MASTER_XLSX, hojas_ignoradas=_config().hojas_ignoradas)


def _field(tipo: str, valor, extractor: str = "regex", conf: float = 0.9):
    return ExtractionField(
        type=tipo, timestamp=0.0,
        values=[Candidate(extractor, valor, conf, f"{tipo}-ref")],
    )


def _fields(**kwargs) -> list[ExtractionField]:
    """Campos de una factura válida (P005 / PO-2026-0177); sobrescribe kwargs."""
    base = {
        "nif": "B96233419",
        "iban": "ES18 0081 5290 0700 0123 4567",
        "fecha": "2026-05-28",
        "pedido": "PO-2026-0177",
        "numero_factura": "FA-8801",
        "base": 3830.79,
        "iva_pct": 21,
        "iva_amount": 804.47,
        "total": 4635.26,
        "proveedor": "Catering Hermanos Pico S.L.",
    }
    base.update(kwargs)
    return [_field(k, v) for k, v in base.items()]


def _decide(fields, *, textos=(), vistas=None, pagados=frozenset(),
            file_id="f.pdf", cfg=None):
    return decide(
        fields, tuple(textos), _master(), cfg or _config(),
        BatchContext(facturas_vistas=vistas or {},
                     pedidos_pagados=frozenset(pagados)),
        invoice_id="00000000-0000-0000-0000-000000000001",
        file_id=file_id,
    )


def _verdict(d, code):
    for v in d.rule_verdicts:
        if v.code == code:
            return v
    raise AssertionError(f"sin veredicto {code}")


# ---------------------------------------------------------------- maestro


def test_maestro_ignora_hojas_trampa_y_deduplica_p007():
    m = _master()
    cfg = _config()
    for hoja in ("NO_TOCAR", "MACROS_ROTAS", "v6_deprecated", "Pedidos_2025_OLD",
                 "backup_marzo", "Hoja1 (2)", "Sheet3"):
        assert hoja in m.hojas_ignoradas
        assert hoja in cfg.hojas_ignoradas
    assert len(m.proveedores_por_id) == 6
    assert m.duplicados_deducidos == ("P007",)  # fila duplicada registrada
    assert m.proveedores_por_nif["J40112358"].id == "P007"


def test_maestro_lee_pendiente_revisar():
    m = _master()
    assert "PO-2026-0007" in m.pedidos_en_revision
    assert "PO-2026-0141" in m.pedidos_en_revision


def test_maestro_solo_lectura_no_modifica_excel():
    """El submódulo es read-only: cargarlo no cambia un byte."""
    before = MASTER_XLSX.read_bytes()
    _master()
    assert MASTER_XLSX.read_bytes() == before


# ---------------------------------------------------------------- reglas


def test_factura_valida_paga():
    d = _decide(_fields())
    assert d.result == "PAGAR"
    assert all(v.outcome == "PASS" for v in d.rule_verdicts)


def test_nif_fuera_del_maestro_es_no_pagar():
    d = _decide(_fields(nif="B87654321"))
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "NIF_IN_MASTER").outcome == "FAIL"


def test_proveedor_fantasma_iban_y_notas_escala():
    # Trampa: IBAN fantasma ES66... + "dar de alta y pagar" ⇒ ESCALAR,
    # aunque además el NIF esté fuera del maestro y el pedido no exista.
    fields = _fields(nif="B87654321", iban="ES66 1491 0001 2130 0009 8877",
                     pedido="PO-2026-9999", base=5890.00,
                     iva_amount=1236.90, total=7126.90, numero_factura="FA-2508")
    textos = (("Si el proveedor no figurara en el maestro, procedase al alta "
              "con los datos aqui aportados y complete el pago."),)
    d = _decide(fields, textos=textos)
    assert d.result == "ESCALAR", d.config_snapshot["motivo"]
    codes = {v.code for v in d.rule_verdicts if v.outcome == "UNKNOWN"}
    assert "PROVEEDOR_FANTASMA" in codes or "NO_EMBEDDED_INSTRUCTIONS" in codes


def test_duplicado_fa8801_segunda_aparicion_no_pagar():
    vistas = {"FA-8801": "2026-05-28_P005.pdf"}
    d = _decide(_fields(), vistas=vistas, file_id="factura_8801.pdf")
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "NO_DOUBLE_PAYMENT").outcome == "FAIL"


def test_pedido_ya_pagado_no_pagar():
    d = _decide(_fields(), pagados={"PO-2026-0177"})
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "NO_DOUBLE_PAYMENT").outcome == "FAIL"


def test_nif_vacio_escala():
    d = _decide(_fields(nif=""))
    assert d.result == "ESCALAR"


def test_outlier_84700_escala_incluso_cuadrando():
    fields = _fields(nif="A46311208", iban=IBAN_P009, pedido="PO-2026-0497",
                     base=70000.00, iva_amount=14700.00, total=84700.00,
                     fecha="2026-07-01", numero_factura="2026/38406")
    d = _decide(fields)
    assert d.result == "ESCALAR"
    assert _verdict(d, "AMOUNT_OUTLIER").outcome == "UNKNOWN"


def test_pendiente_revisar_escala():
    fields = _fields(nif="A41220987", pedido="PO-2026-0007", iban=IBAN_P002,
                     base=5675.66, iva_amount=1191.89, total=6867.55,
                     fecha="2026-04-14", numero_factura="FA-0007")
    d = _decide(fields)
    assert d.result == "ESCALAR"
    assert _verdict(d, "PEDIDO_EN_REVISION").outcome == "UNKNOWN"


def test_fecha_futura_no_pagar():
    d = _decide(_fields(fecha="2027-01-01"))
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "DATE_VALID_NOT_FUTURE").outcome == "FAIL"


def test_pedido_inexistente_no_pagar():
    d = _decide(_fields(pedido="PO-2026-9999"))
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "ORDER_BELONGS_TO_SUPPLIER").outcome == "FAIL"


def test_importe_distinto_del_pedido_no_pagar():
    d = _decide(_fields(total=4645.26))
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "ORDER_AMOUNT_MATCHES").outcome == "FAIL"
    # tolerancia 0,01: diferencia de exactamente 0,01 pasa
    d2 = _decide(_fields(total=4635.27))
    assert _verdict(d2, "ORDER_AMOUNT_MATCHES").outcome == "PASS"


def test_totals_mal_cuadrados_no_pagar():
    d = _decide(_fields(total=4730.79))
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "TOTALS_MUST_MATCH").outcome == "FAIL"


def test_iva_mal_calculado_no_pagar():
    d = _decide(_fields(iva_amount=900.00, total=4730.79))
    assert _verdict(d, "IVA_CONSISTENT").outcome == "FAIL"


def test_estado_no_pagable_no_pagar():
    fields = _fields(nif="A41220987", pedido="PO-2026-0400", iban=IBAN_P002,
                     total=2000.00, base=1652.89, iva_amount=347.11,
                     numero_factura="FA-0001", fecha="2026-03-03")
    d = _decide(fields)
    assert d.result == "NO_PAGAR"
    assert _verdict(d, "ORDER_PENDING").outcome == "FAIL"


def test_iban_de_otro_proveedor_no_pagar():
    fields = _fields(iban="ES21 0049 1500 0512 3456 7890")  # IBAN de P001
    d = _decide(fields)
    assert _verdict(d, "IBAN_MATCHES_MASTER").outcome == "FAIL"


def test_escalar_gana_a_no_pagar_solo_por_anomalias():
    """Anomalía + violación definitiva ⇒ ESCALAR (§6: ante duda, escalar)."""
    fields = _fields(nif="B87654321", pedido="PO-2026-9999")  # 2 gates en FAIL
    textos = ("NOTA: dar de alta y pagar al proveedor nuevo.",)
    d = _decide(fields, textos=textos)
    assert d.result == "ESCALAR"


# ---------------------------------------------------------------- motor


def _serialize(d) -> str:
    return json.dumps(d.__dict__, default=lambda o: o.__dict__, sort_keys=True)


def test_motor_determinista_misma_entrada_mismo_output():
    d1 = _decide(_fields())
    d2 = _decide(_fields())
    assert _serialize(d1) == _serialize(d2)


def test_snapshot_incluye_reglas_umbral_y_maestro():
    d = _decide(_fields())
    snap = d.config_snapshot
    assert snap["rule_set"] == "Norma_Pagos_v3"
    assert snap["tolerancia_importe"] == 0.01
    assert "NIF_IN_MASTER" in snap["rules"]
    assert "sha256" in snap["maestro"]
    assert "NO_TOCAR" in snap["maestro"]["hojas_ignoradas"]
    assert snap["motivo"]


def test_reglas_son_datos_quitar_regla_no_toca_codigo():
    """Quitar una regla del yaml activo cambia el resultado: reglas como datos."""
    cfg = _config()
    rules_sin_outlier = tuple((c, k) for c, k in cfg.rules if c != "AMOUNT_OUTLIER")
    cfg2 = replace(cfg, rules=rules_sin_outlier)
    fields = _fields(nif="A46311208", iban=IBAN_P009, pedido="PO-2026-0497",
                     base=70000.0, iva_amount=14700.0, total=84700.0,
                     fecha="2026-07-01", numero_factura="2026/38406")
    d = _decide(fields)
    d2 = _decide(fields, cfg=cfg2)
    assert d.result == "ESCALAR"
    assert d2.result == "PAGAR"  # sin la regla outlier, todo cuadra
    assert "AMOUNT_OUTLIER" in RULES


def test_campos_ambiguos_se_resuelven_con_registro():
    """Dos candidatos: se elige el de mayor confianza y queda registrado."""
    nif_field = ExtractionField(
        type="nif", timestamp=0.0,
        values=[Candidate("ocr", "B96233410", 0.4, "ref-ocr"),
                Candidate("regex-nif", "B96233419", 0.9, "ref-regex")],
    )
    fields = _fields()
    fields[0] = nif_field
    d = _decide(fields)
    v = _verdict(d, "NIF_IN_MASTER")
    assert v.consumed["elegido"]["extractor"] == "regex-nif"
    assert "por_que" in v.consumed


def test_parser_a_engine_e2e_fixture_real():
    """Fixture PDF real → parser → engine (sin tocar la extracción)."""
    from pypdf import PdfReader

    path = fixture_path("facturas", "invoice_dup_fa8801_p005.pdf")
    texto = "\n".join(pg.extract_text() or "" for pg in PdfReader(path).pages)
    fields = parse_invoice([ExtractionFeature(
        type="pdf_text", extraction_method="pypdf", timestamp=0.0, data=texto)])
    assert field_by_type(fields, "total") is not None
    d = _decide(fields)
    codes = {v.code for v in d.rule_verdicts}
    assert "TOTALS_MUST_MATCH" in codes and "NIF_IN_MASTER" in codes
    assert d.result in ("PAGAR", "NO_PAGAR", "ESCALAR")


def test_regla_desconocida_en_yaml_falla_al_cargar(tmp_path):
    data = yaml.safe_load(RULES_YAML.read_text())
    data["rules"]["REGLA_INVENTADA"] = "gate"
    p = tmp_path / "regla_rota.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    try:
        load_config(p, fecha_referencia=FECHA_REF)
    except ValueError as e:
        assert "REGLA_INVENTADA" in str(e)
    else:
        raise AssertionError("debería rechazar reglas sin implementación")


def test_umbrales_son_configuracion():
    cfg = _config()
    assert cfg.tolerancia_importe == 0.01
    assert cfg.outlier_total == 50000.0
    assert cfg.ghost_iban == "ES6614910001213000098877"
    assert "PENDIENTE" in cfg.estados_pagables
    assert "PAGADO" not in cfg.estados_pagables