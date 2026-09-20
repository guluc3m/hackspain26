"""The resident PouchDB bridge: one warm Node child per root, batched reads."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from filemaid.store.pouch import PouchStore

KILL = getattr(signal, "SIGKILL", signal.SIGTERM)


def _put(store: PouchStore, index: int) -> str:
    doc_id = f"event:scan-{index}"
    store.put(
        {
            "_id": doc_id,
            "kind": "event",
            "file_id": f"factura-{index}.pdf",
            "file_key": f"key-{index}",
            "invoice_id": "invoice",
            "scan_id": f"scan-{index}",
            "type": "invoice_seen",
            "timestamp": float(index),
        }
    )
    return doc_id


def test_batch_equals_the_same_reads_one_by_one(tmp_path):
    store = PouchStore(tmp_path / "data")
    ids = [_put(store, index) for index in range(5)]
    requests = [
        {"op": "get", "id": doc_id} for doc_id in [*ids, "event:missing"]
    ] + [{"op": "list", "prefix": "event:"}, {"op": "list", "prefix": "nothing:"}]

    assert store.batch(requests) == [
        *(store.get(doc_id) for doc_id in [*ids, "event:missing"]),
        store.list("event:"),
        store.list("nothing:"),
    ]
    assert store.batch([]) == []


def test_consecutive_requests_reuse_one_bridge_process(tmp_path):
    store = PouchStore(tmp_path / "data")
    first = store.request(op="ping")["pid"]

    _put(store, 1)
    assert store.get("event:scan-1")["file_id"] == "factura-1.pdf"
    assert store.batch([{"op": "list", "prefix": "event:"}])[0][0]["_id"] == "event:scan-1"

    assert store.request(op="ping")["pid"] == first


def test_killed_bridge_is_restarted_transparently(tmp_path):
    store = PouchStore(tmp_path / "data")
    _put(store, 1)
    pid = store.request(op="ping")["pid"]

    os.kill(pid, KILL)

    assert store.get("event:scan-1")["file_id"] == "factura-1.pdf"
    assert store.request(op="ping")["pid"] != pid
    assert store.get("event:scan-1")["_id"] == "event:scan-1"


def test_batch_raises_on_a_failing_operation(tmp_path):
    store = PouchStore(tmp_path / "data")
    _put(store, 1)

    with pytest.raises(RuntimeError, match="Invalid decision result"):
        store.batch(
            [
                {"op": "get", "id": "event:scan-1"},
                {
                    "op": "put",
                    "doc": {"_id": "decision:x", "kind": "decision", "decision": {"result": "?"}},
                },
            ]
        )

    # The bridge stays usable after a rejected operation.
    assert store.get("event:scan-1")["_id"] == "event:scan-1"


def test_a_bridge_that_stops_answering_is_restarted(tmp_path, monkeypatch):
    from filemaid.store import pouch

    store = PouchStore(tmp_path / "data")
    _put(store, 1)
    pid = store.request(op="ping")["pid"]

    monkeypatch.setattr(pouch, "REQUEST_TIMEOUT_S", 1e-6)  # no exchange can answer that fast
    with pytest.raises(RuntimeError, match="PouchDB bridge failed"):
        store.get("event:scan-1")
    monkeypatch.undo()

    assert store.get("event:scan-1")["_id"] == "event:scan-1"
    assert store.request(op="ping")["pid"] != pid


# A warm bridge must hold nothing on disk between requests, or it would starve
# the second process (CLI vs UI) the lock file exists to serialise: opening the
# store, its view index, and a write from a separate interpreter.
_CHILD = """
import sys
sys.path.insert(0, sys.argv[2])
from pathlib import Path
from filemaid.store.pouch import PouchStore

store = PouchStore(Path(sys.argv[1]))
assert [e["_id"] for e in store.for_file("factura-1.pdf", "event")] == ["event:scan-1"]
store.put(
    {
        "_id": "event:second",
        "kind": "event",
        "file_id": "factura-1.pdf",
        "file_key": "key-1",
        "invoice_id": "invoice",
        "scan_id": "scan-1",
        "type": "invoice_seen",
        "timestamp": 9.0,
    }
)
assert store.get("event:second")["_id"] == "event:second"
print("ok")
"""


def test_a_second_process_may_use_the_same_root(tmp_path):
    root = tmp_path / "data"
    store = PouchStore(root)
    _put(store, 1)
    # Warm the bridge and materialise the view index before the child starts.
    assert store.for_file("factura-1.pdf", "event")[0]["_id"] == "event:scan-1"

    child = subprocess.run(
        [sys.executable, "-c", _CHILD, str(root), str(Path(__file__).resolve().parents[1] / "src")],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert child.returncode == 0, child.stderr
    assert child.stdout.strip() == "ok"
    assert store.for_file("factura-1.pdf", "event")[0]["_id"] == "event:scan-1"
    assert store.get("event:second")["_id"] == "event:second"
