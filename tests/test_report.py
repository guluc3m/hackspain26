from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from filemaid.rules.engine import evaluate
from filemaid.rules.report import collect_run, write_report
from filemaid.store.trace import ScanTrace
from filemaid.types import ExtractionField


def _field(tipo: str, valor, conf: float = 0.9, extractor: str = "test") -> ExtractionField:
    f = ExtractionField(type=tipo)
    f.add(extractor, valor, conf)
    return f


def _fields_ok() -> dict[str, ExtractionField]:
    return {
        "nif": _field("nif", "B12345678"),
        "iban": _field("iban", "ES9121000418450200051332"),
        "total": _field("total", 121.00),
        "pedido": _field("pedido", "P-2026-001"),
        "iva_amount": _field("iva_amount", 21.00),
        "iva_rate": _field("iva_rate", 21),
        "fecha": _field("fecha", "01/01/2026"),
    }


def _persist(store, master, rule_config, invoice_id: str, file_id: str, fields: dict, config_version: str | None = None) -> None:
    d = evaluate(fields, master, rule_config, invoice_id, file_id)
    version = config_version or rule_config.version
    trace = ScanTrace(store, Path(file_id), f"sha-{invoice_id}", invoice_id)
    with trace.active():
        trace.begin(version, "extract-v1", master.sha256)
        trace.fields(list(fields.values()), 10)
        trace.decision(d, version)


def _lote(store, master, rule_config) -> None:
    _persist(store, master, rule_config, "inv-ok", "a.pdf", _fields_ok())

    no_pagar = _fields_ok()
    no_pagar["nif"] = _field("nif", "B00000000")  # formato válido, fuera de maestro
    _persist(store, master, rule_config, "inv-no", "b.pdf", no_pagar)

    escalar = _fields_ok()
    del escalar["fecha"]  # sin fecha: UNKNOWN ⇒ duda razonable
    _persist(store, master, rule_config, "inv-esc", "c.pdf", escalar)


def test_collect_run_resumen_por_resultado(store, cfg, master, rule_config):
    _lote(store, master, rule_config)
    run = collect_run(store, cfg, rule_config.version)
    assert run["counts"] == {"PAGAR": 1, "NO_PAGAR": 1, "ESCALAR": 1}
    assert not run["config_mismatch"]
    assert run["rule_stats"] == [
        {
            "code": "DATE_VALID_NOT_FUTURE",
            "total": 1,
            "FAIL": 0,
            "UNKNOWN": 1,
            "reasons": {"SIN_CAMPO": 1},
            "reason_list": [("SIN_CAMPO", "sin campo", 1)],
        },
        {
            "code": "ORDER_BELONGS_TO_SUPPLIER",
            "total": 1,
            "FAIL": 1,
            "UNKNOWN": 0,
            "reasons": {},
            "reason_list": [],
        },
    ]
    por_id = {inv["invoice_id"]: inv for inv in run["invoices"]}
    assert por_id["inv-no"]["drivers"][0]["code"] == "ORDER_BELONGS_TO_SUPPLIER"
    assert por_id["inv-esc"]["drivers"][0]["code"] == "DATE_VALID_NOT_FUTURE"
    assert por_id["inv-ok"]["drivers"] == []
    assert por_id["inv-ok"]["driver_kind"].startswith("todas las reglas PASS")


def test_collect_run_avisa_si_la_config_del_run_no_es_la_actual(store, cfg, master, rule_config):
    _persist(store, master, rule_config, "inv-ok", "a.pdf", _fields_ok(), config_version="otra-version")
    run = collect_run(store, cfg, "otra-version")
    assert run["config_mismatch"]


def test_breadcrumbs_cada_candidato_con_su_suerte(store, cfg, master, rule_config):
    fields = _fields_ok()
    fields["nif"] = _field(
        "nif", "XX12345678", conf=0.95, extractor="tesseract"
    )  # formato inválido
    fields["nif"].add("pypdf", "B12345678", 0.8)  # elegido
    fields["nif"].add("vlm", "B12345678", 0.25)  # bajo el umbral de puntuación
    _persist(store, master, rule_config, "inv-bread", "d.pdf", fields)
    run = collect_run(store, cfg, rule_config.version)
    inv = next(i for i in run["invoices"] if i["invoice_id"] == "inv-bread")
    nif = next(f for f in inv["fields"] if f["type"] == "nif")
    por_extractor = {c["extractor"]: c for c in nif["candidates"]}
    assert por_extractor["tesseract"]["status"].startswith("RECHAZADO_FORMATO")
    assert por_extractor["vlm"]["status"] == "RECHAZADO_UMBRAL"
    assert por_extractor["pypdf"]["status"] == "ELEGIDO"
    assert nif["chosen"]["value"] == "B12345678"
    assert nif["chosen"]["why"]  # procedencia: confianza × peso


def test_reporte_fail_escalado_no_es_negativo_definitivo(store, cfg, master, rule_config):
    # NIF fuera de maestro (config: FAIL→ESCALAR) y pedido ausente: hay dudas,
    # pero ninguna regla resuelve NO_PAGAR ⇒ ESCALAR, con la NIF como driver.
    fields = _fields_ok()
    fields["nif"] = _field("nif", "B00000000")
    del fields["pedido"]
    _persist(store, master, rule_config, "inv-nif", "e.pdf", fields)
    run = collect_run(store, cfg, rule_config.version)
    inv = next(i for i in run["invoices"] if i["invoice_id"] == "inv-nif")
    assert inv["result"] == "ESCALAR"
    assert "NIF_IN_MASTER" in {e["code"] for e in inv["drivers"]}
    assert "FAIL→ESCALAR" in inv["driver_kind"]


def test_write_report_html_y_jsonl(store, cfg, master, rule_config, tmp_path):
    _lote(store, master, rule_config)
    out = write_report(store, cfg, rule_config.version, tmp_path / "rules")

    index = (out / "index.html").read_text(encoding="utf-8")
    assert "a.pdf" in index and "b.pdf" in index and "c.pdf" in index
    for resultado in ("PAGAR", "NO_PAGAR", "ESCALAR"):
        assert resultado in index
    assert "Errores comunes" in index
    assert "DATE_VALID_NOT_FUTURE" in index and "ORDER_BELONGS_TO_SUPPLIER" in index
    assert "sin campo" in index  # tipo de UNKNOWN del informe ESCALAR
    assert "latencia media" in index
    assert "extracción · parser · reglas" in index

    detalle = (out / "facturas" / "inv-no.html").read_text(encoding="utf-8")
    assert "NIF_IN_MASTER" in detalle and "NO_PAGAR" in detalle
    assert "IVA_CONSISTENT" in detalle  # el resto de reglas también se listan
    assert "TOTALS_MUST_MATCH" in detalle

    inv_ok = (out / "facturas" / "inv-ok.html").read_text(encoding="utf-8")
    assert "ELEGIDO" in inv_ok
    assert "latencia total" in inv_ok
    assert "extracción (escalera)" in inv_ok
    assert "parser (candidatos)" in inv_ok
    assert "evaluación de reglas" in inv_ok

    lineas = [
        json.loads(l) for l in (out / "detalle.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(lineas) == 3
    assert {l["result"] for l in lineas} == {"PAGAR", "NO_PAGAR", "ESCALAR"}
    assert all("fields" in l and "evaluations" in l for l in lineas)
    assert all("extraction_ms" in l and "parser_ms" in l and "evaluation_ms" in l and "total_ms" in l for l in lineas)
