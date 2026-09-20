"""HTTP wiring for the review/dispute routes in api/app.py."""

from __future__ import annotations

from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.pipeline import Pipeline
from filemaid.store import queries
from filemaid.store.pouch import PouchStore
from test_smoke_pipeline import _make_text_pdf

ESCALAR_TEXT = (
    "FACTURA Suministros Garcia SL TOTAL 121,00 EUR Fecha 15/01/2026 Base 100,00 EUR IVA 21,00 EUR"
)


def _escalated(cfg, tmp_path) -> tuple[str, str]:
    source = tmp_path / "esc.pdf"
    _make_text_pdf(source, ESCALAR_TEXT)
    Pipeline(cfg).process_pdf(source)
    store = PouchStore(cfg.root)
    row = next(r for r in queries.invoice_rows(store) if r["file_id"] == "esc.pdf")
    assert row["result"] == "ESCALAR"
    return row["id"], row["decision_id"]


def test_revision_routes_list_detail_and_resolve(cfg, tmp_path) -> None:
    key, decision_id = _escalated(cfg, tmp_path)
    app = create_app(cfg)
    with TestClient(app) as client:
        listing = client.get("/api/revision").json()
        assert [item["file_key"] for item in listing["items"]] == [key]

        detail = client.get(f"/api/revision/{key}").json()
        assert detail["disputed"] is True
        assert detail["review_state"] == "pending"

        stale = client.post(
            f"/api/revision/{key}/resolve",
            json={"who": "a", "reason": "x", "expected_decision_id": "decision:other"},
        )
        assert stale.status_code == 409

        extra = client.post(
            f"/api/revision/{key}/resolve",
            json={"who": "a", "reason": "x", "expected_decision_id": decision_id, "bogus": 1},
        )
        assert extra.status_code == 422

        missing = client.post(f"/api/revision/{key}/resolve", json={"who": "a", "reason": "x"})
        assert missing.status_code == 422

        ok = client.post(
            f"/api/revision/{key}/resolve",
            json={"who": "alice", "reason": "revisado", "expected_decision_id": decision_id},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["review_state"] == "resolved"
        assert body["disputed"] is False
        assert body["result"] in {"PAGAR", "NO_PAGAR", "ESCALAR"}

        assert client.get("/api/revision").json()["items"] == []
        assert client.get(f"/api/revision/{key}").json()["disputed"] is False


def test_revision_detail_unknown_is_404(cfg) -> None:
    app = create_app(cfg)
    with TestClient(app) as client:
        assert client.get("/api/revision/nope").status_code == 404


def test_legacy_override_route_is_removed(cfg, tmp_path) -> None:
    key, _ = _escalated(cfg, tmp_path)
    app = create_app(cfg)
    with TestClient(app) as client:
        response = client.post(
            f"/api/revision/{key}/override",
            json={"field_type": "total", "before": "1", "after": "1", "who": "a"},
        )
        # The legacy override POST is gone: the request is rejected and the dispute survives.
        assert not response.is_success
        assert client.get(f"/api/revision/{key}").json()["disputed"] is True
