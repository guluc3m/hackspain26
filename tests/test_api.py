"""API: facturas enriquecidas (carpeta, iteraciones, confianza) y log finder."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from albertitos.api.app import create_app
from albertitos.store.ledger import Ledger


def _client(cfg):
    return TestClient(create_app(cfg))


def test_facturas_incluye_carpeta_iteraciones_y_confianza(cfg, store):
    store.upsert_invoice("inv-1", "f.pdf", "sha-1", source_path="/lotes/a/f.pdf")
    store.add_field(
        "inv-1",
        "total",
        [
            {"extractor": "regex", "value": 121.0, "confidence": 0.9},
            {"extractor": "ocr", "value": 121.0, "confidence": 0.5},
        ],
    )
    store.save_decision("inv-1", "rules", "ESCALAR", {})
    Ledger(cfg.ledger_path).append(
        "decision", {"invoice_id": "inv-1", "file_id": "f.pdf", "result": "ESCALAR", "run_id": "rules"}
    )

    rows = _client(cfg).get("/api/facturas").json()
    assert len(rows) == 1
    r = rows[0]
    assert r["file_id"] == "f.pdf"
    assert r["folder"] == "/lotes/a"
    assert r["source_path"] == "/lotes/a/f.pdf"
    assert r["result"] == "ESCALAR"
    assert r["decided_at"] is not None
    assert r["iterations"] == 1
    # mejor candidato por campo (0.9), luego el peor campo -> 0.9
    assert r["confidence"] == 0.9


def test_facturas_sin_decision_confianza_nula(cfg, store):
    store.upsert_invoice("inv-2", "g.pdf", "sha-2")
    rows = _client(cfg).get("/api/facturas").json()
    r = rows[0]
    assert r["status"] == "pendiente"
    assert r["result"] is None
    assert r["confidence"] is None
    assert r["iterations"] == 0
    assert r["folder"] is None


def test_logs_orden_filtro_y_linea_corrupta(cfg):
    ledger = Ledger(cfg.ledger_path)
    ledger.append("invoice_seen", {"invoice_id": "inv-1", "file_id": "f.pdf", "sha256": "sha-1"})
    ledger.append("decision", {"invoice_id": "inv-1", "file_id": "f.pdf", "result": "PAGAR", "run_id": "rules"})
    # línea truncada por una caída: la lectura debe tolerarla
    with ledger.path.open("a", encoding="utf-8") as f:
        f.write('{"type": "decision", "resul')

    c = _client(cfg)
    data = c.get("/api/logs").json()
    assert data["total"] == 2
    assert data["types"] == ["decision", "invoice_seen"]
    # más recientes primero, con seq en orden append-only
    assert [e["seq"] for e in data["items"]] == [2, 1]
    assert data["items"][0]["type"] == "decision"
    assert data["items"][0]["ts"] is not None

    solo_decision = c.get("/api/logs", params={"event_type": "decision"}).json()
    assert solo_decision["total"] == 1
    assert solo_decision["items"][0]["result"] == "PAGAR"

    por_q = c.get("/api/logs", params={"q": "f.pdf"}).json()
    assert por_q["total"] == 2
    sin_match = c.get("/api/logs", params={"q": "no-existe"}).json()
    assert sin_match["total"] == 0


def test_logs_paginado_desde_el_mas_reciente(cfg):
    ledger = Ledger(cfg.ledger_path)
    for i in range(5):
        ledger.append("invoice_seen", {"invoice_id": f"inv-{i}", "file_id": f"f{i}.pdf"})
    c = _client(cfg)
    p1 = c.get("/api/logs", params={"limit": 2}).json()
    assert [e["seq"] for e in p1["items"]] == [5, 4]
    p2 = c.get("/api/logs", params={"limit": 2, "offset": 2}).json()
    assert [e["seq"] for e in p2["items"]] == [3, 2]


def test_override_factura_inexistente_404(cfg):
    r = _client(cfg).post(
        "/api/revision/no-existe/override",
        json={"field_type": "iban", "before": "a", "after": "b", "who": "revisor"},
    )
    assert r.status_code == 404


def test_reprocesar_file_desconocido_404(cfg):
    r = _client(cfg).post("/api/reprocesar/ninguno.pdf")
    assert r.status_code == 404


def test_reglas_expone_config(cfg):
    data = _client(cfg).get("/api/reglas").json()
    assert data["rule_set_version"] == "v1"
    assert "NIF_IN_MASTER" in data["enabled"]
    assert "TOTALS_MUST_MATCH" in data["thresholds"]
    # el JSON de la respuesta es válido y serializable (sanity)
    assert isinstance(json.dumps(data), str)
