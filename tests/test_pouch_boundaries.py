from __future__ import annotations

import pytest

from filemaid.store.pouch import INLINE_LIMIT, PouchStore
from filemaid.store.trace import ScanTrace


def test_large_fields_decision_and_event_roundtrip(tmp_path):
    from filemaid.store.queries import logs

    store = PouchStore(tmp_path / "data")
    trace = ScanTrace(store, tmp_path / "exact ñ.pdf", "sha", "invoice")
    large = "ñ" * INLINE_LIMIT
    payload = {
        "decision": {"result": "ESCALAR", "rule_evaluations": [{"reason": large}]},
        "run_id": "r",
    }
    ref = trace.record("decision", "decision:large", payload)
    stored = store.get(ref)
    assert "payload_ref" in stored
    assert store.hydrate(stored)["decision"] == payload["decision"]
    trace.record(
        "fields", "fields:large", {"fields": [{"type": "total", "values": [{"value": large}]}]}
    )
    assert store.hydrate(store.get("fields:large"))["fields"][0]["values"][0]["value"] == large
    trace.event("item_error", {"error": large})
    assert large in logs(store, invoice="exact ñ.pdf")["items"][0]["resumen"]
    for doc in (
        {"_id": "decision:bad", "kind": "decision", "decision": {"result": "INVALID"}},
        {"_id": ref, "_rev": stored["_rev"], "kind": "decision", "decision": {"result": "PAGAR"}},
        {"_id": ref, "_deleted": True},
    ):
        with pytest.raises(RuntimeError):
            store.put(doc)
    assert store.hydrate(store.get(ref))["decision"]["result"] == "ESCALAR"
