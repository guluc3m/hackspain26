from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.pipeline import Pipeline, outcomes_from_store
from filemaid.rules.report import write_report
from filemaid.store.pouch import PouchStore
from filemaid.store.queries import invoice_rows
from test_smoke_pipeline import _make_text_pdf


def test_same_basename_reprocess_and_report_use_exact_scan(cfg, tmp_path):
    one = tmp_path / "one"
    two = tmp_path / "two"
    one.mkdir()
    two.mkdir()
    filename = "misma factura.pdf"
    _make_text_pdf(one / filename, "FACTURA NIF B12345678 TOTAL 121,00 EUR Fecha 15/01/2026")
    _make_text_pdf(two / filename, "FACTURA NIF Z99999999 TOTAL 999,00 EUR Fecha 15/01/2026")
    pipe = Pipeline(cfg)
    first = pipe.process_pdf(one / filename)
    pipe.process_pdf(two / filename)
    store = PouchStore(cfg.root)
    rows = invoice_rows(store)
    assert len(rows) == 2
    with pytest.raises(ValueError, match="Ambiguous filename"):
        outcomes_from_store(store, pipe.rule_config.version)
    first_key = next(
        r["file_key"] for r in store.list("file:") if r["invoice_id"] == first.invoice_id
    )
    first_scan = store.list(f"scan:{first_key}:")[0]
    stored_copy = cfg.root / "scans" / first_scan["scan_id"] / filename
    stored_copy.unlink()
    (one / filename).unlink()
    client = TestClient(create_app(cfg))
    assert client.post(f"/api/reprocesar/{filename}", json={}).status_code == 409
    response = client.post(f"/api/reprocesar/{filename}", params={"file_key": first_key}, json={})
    assert response.status_code == 200, response.text
    assert response.json()["result"] == first.result
    assert len(store.list(f"scan:{first_key}:")) == 2
    report = write_report(pipe.store, cfg, pipe.rule_config.version, tmp_path / "reports")
    latest = {}
    for doc in sorted(store.list("decision:"), key=lambda d: d["timestamp"]):
        latest[doc["file_key"]] = doc
    decisions = latest.values()
    for row in decisions:
        artifacts = [
            d
            for d in store.for_file(filename, "artifact")
            if d["scan_id"] == row["scan_id"] and d["stage"] == "report"
        ]
        assert {d["name"] for d in artifacts} == {
            "index.html",
            "detalle.jsonl",
            f"{row['scan_id']}.html",
        }
        detail = next(d for d in artifacts if d["name"] == "detalle.jsonl")
        assert (
            b"".join(store.read_artifact(detail["_id"])) == (report / "detalle.jsonl").read_bytes()
        )
    # The superseded first scan must not be relabelled as this report's execution.
    assert not any(
        d["stage"] == "report" and d["scan_id"] == first_scan["scan_id"]
        for d in store.for_file(filename, "artifact")
    )
