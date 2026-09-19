from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.pipeline import Pipeline
from filemaid.store.pouch import CHUNK_SIZE, PouchStore
from filemaid.store.queries import invoice_rows
from test_smoke_pipeline import _make_text_pdf

TEXT = (
    "FACTURA Suministros García SL NIF B12345678 TOTAL 121,00 EUR "
    "Fecha 15/01/2026 Pedido P-2026-001 Base 100,00 EUR IVA 21,00 EUR"
)


def test_scan_persists_complete_evidence_and_aliases(cfg, tmp_path):
    first = tmp_path / "Factura ñ exacta.PDF"
    second = tmp_path / "Factura copia.pdf"
    _make_text_pdf(first, TEXT)
    source_bytes = first.read_bytes()
    second.write_bytes(source_bytes)
    pipe = Pipeline(cfg)
    outcomes = tmp_path / "outcomes.jsonl"
    batch = pipe.run_lote(tmp_path, outcomes)
    original = next(d for d in batch if d.file_id == first.name)
    pipe.process_pdf(first)
    store = PouchStore(cfg.root)  # re-open actual disk engine, not an in-memory substitute
    records = store.for_file(first.name)
    decisions = [store.hydrate(d) for d in records if d["kind"] == "decision"]
    assert len(decisions) == 2
    assert len({d["_id"] for d in decisions}) == 2
    assert decisions[0]["decision"] == asdict(original)
    assert all(d["file_id"] == first.name for d in records)
    assert len(store.for_file(second.name, "decision")) == 1
    fields = next(d for d in records if d["kind"] == "fields")
    assert next(f for f in fields["fields"] if f["type"] == "total")["values"]
    text = next(d for d in records if d["kind"] == "feature")["feature"]["data"]
    assert "FACTURA" in text and "121,00" in text
    input_artifact = next(d for d in records if d["kind"] == "artifact" and d["stage"] == "input")
    export = next(d for d in records if d["kind"] == "artifact" and d["stage"] == "export")
    assert b"".join(store.read_artifact(export["_id"])) == outcomes.read_bytes()
    first.unlink()
    assert b"".join(store.read_artifact(input_artifact["_id"])) == source_bytes
    assert {r["file_id"] for r in invoice_rows(store)} == {first.name, second.name}
    client = TestClient(create_app(cfg))
    logs = client.get("/api/logs", params={"invoice": first.name}).json()
    assert {e["file_id"] for e in logs["items"]} == {first.name}
    assert {e["type"] for e in logs["items"]} >= {"invoice_seen", "feature", "fields", "decision"}
    assert client.get("/api/logs", params={"invoice": "Factura"}).json()["items"] == []
    assert any(d["kind"] == "decision" for d in store.list("decision:"))


def test_chunked_attachments_concurrency_and_immutability(tmp_path):
    store = PouchStore(tmp_path / "data")
    identity = {"scan_id": "scan", "file_id": "a.pdf", "file_key": "key", "invoice_id": "invoice"}
    data = b"A" * CHUNK_SIZE + b"B" * CHUNK_SIZE + b"last"
    with ThreadPoolExecutor(max_workers=3) as pool:
        ids = list(
            pool.map(
                lambda _: store.artifact(identity, "input", "a.pdf", data, "application/pdf"),
                range(3),
            )
        )
    assert all(b"".join(store.read_artifact(id)) == data for id in ids)
    decision = {
        "_id": "decision:scan",
        "kind": "decision",
        "decision": {"result": "ESCALAR"},
        **identity,
    }
    store.put(decision)
    rev = store.get(decision["_id"])["_rev"]
    store.put(decision)
    assert store.get(decision["_id"])["_rev"] == rev
    with pytest.raises(RuntimeError, match="collision"):
        store.put({**decision, "decision": {"result": "PAGAR"}})
    assert store.get(decision["_id"])["decision"]["result"] == "ESCALAR"
    assert len(store.for_file("a.pdf", "artifact")) == 3


def test_partial_scan_keeps_previous_rungs_and_error(cfg, tmp_path, monkeypatch):
    from filemaid.extract import ladder
    from filemaid.types import ExtractionFeature

    source = tmp_path / "broken.pdf"
    _make_text_pdf(source, TEXT)

    def fail(_ctx):
        raise RuntimeError("later rung failed")

    monkeypatch.setattr(
        ladder,
        "_RUNGS",
        [
            (
                "first",
                lambda ctx: ExtractionFeature(
                    type="pdf_text", extraction_method="first", data="retained"
                ),
                False,
                ladder._wrap_text,
            ),
            ("later", fail, False, None),
        ],
    )
    pipe = Pipeline(cfg)
    with pytest.raises(RuntimeError, match="later rung failed"):
        pipe.process_pdf(source)
    records = PouchStore(cfg.root).for_file(source.name)
    assert next(d for d in records if d["kind"] == "feature")["feature"]["data"] == "retained"
    assert any(d["kind"] == "event" and d["type"] == "item_error" for d in records)
    assert not any(d["kind"] == "decision" for d in records)


def test_pouch_local_docs_cas(tmp_path):
    store = PouchStore(tmp_path / "data")
    assert store.local_get("test-key") is None

    store.local_put("test-key", {"mode": "standalone", "val": 1})
    val1 = store.local_get("test-key")
    assert val1 == {"mode": "standalone", "val": 1}

    # Updating with new payload preserves CAS
    store.local_put("test-key", {"mode": "server", "sync_url": "http://127.0.0.1:8000"})
    val2 = store.local_get("test-key")
    assert val2 == {"mode": "server", "sync_url": "http://127.0.0.1:8000"}

    with pytest.raises(RuntimeError, match="Reserved"):
        store.local_put("test-key", {"_rev": "fake", "_id": "fake", "mode": "standalone"})
    assert store.local_get("test-key") == val2
