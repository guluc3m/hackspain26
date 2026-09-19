"""Read projections for the existing Vue contract and CLI, sourced from PouchDB.

Includes the dispute/review derivation used by the review UI and the selective
replication gate: an invoice is *disputed* (withheld from CouchDB replication)
while its latest decision is ``ESCALAR`` and no resolution covers it, or while
it has an unresolved native revision conflict. ``NO_PAGAR`` is a definitive
negative and ``PAGAR`` a clean pass: neither is ever withheld.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .pouch import PouchStore


def scans_for(store: PouchStore, key: str) -> list[dict]:
    return sorted(store.list(f"scan:{key}:"), key=lambda d: (d["timestamp"], d["_id"]))


def decisions_for(store: PouchStore, key: str) -> list[dict]:
    return [
        store.hydrate(d)
        for s in scans_for(store, key)
        if (d := store.get(f"decision:{s['scan_id']}"))
    ]


def all_scans(store: PouchStore) -> list[dict]:
    """Returns all scan documents sorted by timestamp ascending."""
    return sorted(store.list("scan:"), key=lambda d: (d.get("timestamp", 0), d.get("_id", "")))


def decision_for_scan(store: PouchStore, scan_id: str) -> dict | None:
    d = store.get(f"decision:{scan_id}")
    return store.hydrate(d) if d else None


def fields_for_scan(store: PouchStore, scan_id: str) -> list[dict]:
    f = store.get(f"fields:{scan_id}")
    if f is None:
        return []
    hydrated = store.hydrate(f)
    return hydrated.get("fields", [])


def features_for_scan(store: PouchStore, scan_id: str) -> list[dict]:
    features = store.list(f"feature:{scan_id}:")
    return [store.hydrate(feat) for feat in features]


# ---------------------------------------------------------------- review state


def resolutions_for(store: PouchStore, key: str) -> list[dict]:
    """Human resolutions for an invoice, oldest first (immutable, append-only)."""
    return sorted(
        store.list(f"resolution:{key}:"), key=lambda d: (d.get("timestamp", 0), d["_id"])
    )


def review_state_for(store: PouchStore, key: str) -> str:
    """``pending`` | ``resolved`` | ``not_required``, from the bridge selection.

    The bridge computes the state from current documents inside the same locked
    operation as replication, so the UI and the sync gate can never disagree.
    """
    return store.selection()["states"].get(key, "pending")


def resolution_for(store: PouchStore, key: str) -> dict | None:
    """The resolution that covers the invoice's latest decision, if any."""
    decisions = decisions_for(store, key)
    latest = decisions[-1] if decisions else None
    if latest is None:
        return None
    for r in reversed(resolutions_for(store, key)):
        if latest["_id"] in {r.get("resolved_decision_id"), r.get("reviewed_decision_id")}:
            return r
    return None


def _resolution_view(resolution: dict | None) -> dict | None:
    if resolution is None:
        return None
    return {
        "id": resolution["_id"],
        "who": resolution.get("who", ""),
        "reason": resolution.get("reason", ""),
        "accepted": list(resolution.get("accepted", [])),
        "corrected": dict(resolution.get("corrected", {})),
        "reviewed_decision_id": resolution.get("reviewed_decision_id"),
        "resolved_decision_id": resolution.get("resolved_decision_id"),
        "timestamp": resolution.get("timestamp"),
    }


# ---------------------------------------------------------------- selective sync


def withheld_count(store: PouchStore) -> int:
    """Number of invoices currently withheld from replication."""
    return len(store.selection()["withheld_file_keys"])


# ---------------------------------------------------------------- invoice views


def invoice_rows(store: PouchStore) -> list[dict]:
    rows = []
    states = store.selection()["states"]
    for file in store.list("file:"):
        key = file["file_key"]
        scans = scans_for(store, key)
        if not scans:
            continue
        decisions = decisions_for(store, key)
        latest = decisions[-1] if decisions else None
        state = states.get(key, "pending")
        source = scans[-1].get("source_path")
        rows.append(
            {
                "id": key,
                "file_id": file["file_id"],
                "status": latest["decision"]["result"] if latest else "pendiente",
                "source_path": source,
                "folder": str(Path(source).parent) if source else None,
                "result": latest["decision"]["result"] if latest else None,
                "decision_id": latest["_id"] if latest else None,
                "decided_at": latest["timestamp"] if latest else None,
                "iterations": len(decisions),
                "confidence": None,
                "disputed": state == "pending",
                "withheld_from_sync": state == "pending",
                "review_state": state,
            }
        )
    return sorted(rows, key=lambda r: (r["file_id"], r["id"]))


def invoice_detail(store: PouchStore, key: str) -> dict | None:
    file = store.get(f"file:{key}")
    if file is None:
        return None
    scans = scans_for(store, key)
    if not scans:
        return None
    decisions = decisions_for(store, key)
    latest = decisions[-1] if decisions else None
    state = store.selection()["states"].get(key, "pending")
    resolution = resolution_for(store, key)
    scan = next((s for s in scans if latest and s["scan_id"] == latest["scan_id"]), scans[-1])
    fields_doc = store.get(f"fields:{scan['scan_id']}")
    fields_raw = store.hydrate(fields_doc)["fields"] if fields_doc else []

    # Project to Record<string, Candidate[]> expected by UI
    fields_map: dict[str, list[dict]] = {}
    for f in fields_raw:
        f_type = f.get("type", "")
        fields_map[f_type] = f.get("values", [])

    overrides = [
        store.hydrate(d)
        for d in store.for_file(file["file_id"], "event")
        if d.get("file_key") == key and d.get("type") == "override"
    ]

    first_seen = scans[0]["timestamp"] if scans and "timestamp" in scans[0] else None
    last_seen = (
        latest["timestamp"]
        if latest
        else (scans[-1]["timestamp"] if scans and "timestamp" in scans[-1] else None)
    )

    rule_evaluations = []
    if latest and "decision" in latest:
        rule_evaluations = latest["decision"].get("rule_evaluations", [])

    return {
        "invoice": {
            "id": key,
            "file_id": file["file_id"],
            "sha256": file.get("sha256", scan.get("sha256", "")),
            "first_seen": first_seen,
            "last_seen": last_seen,
            "source_path": scan.get("source_path"),
            "status": latest["decision"]["result"] if latest else "pendiente",
        },
        "decision": {
            "decision_id": latest["_id"],
            "invoice_id": key,
            "result": latest["decision"]["result"],
            "timestamp": latest["timestamp"],
        }
        if latest
        else None,
        "fields": fields_map,
        "rule_evaluations": rule_evaluations,
        "overrides": [
            {
                **d["payload"],
                "id": d["_id"],
                "timestamp": d["timestamp"],
                "before": json.dumps(d["payload"]["before"], ensure_ascii=False),
                "after": json.dumps(d["payload"]["after"], ensure_ascii=False),
            }
            for d in overrides
        ],
        "disputed": state == "pending",
        "withheld_from_sync": state == "pending",
        "review_state": state,
        "resolution_id": resolution["_id"] if resolution else None,
        "resolution": _resolution_view(resolution),
    }


# ---------------------------------------------------------------- logs


def _short(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _log_summary(doc: dict) -> str:
    """Short semantic summary; the structured payload travels separately."""
    event_type = doc.get("type", "")
    payload = doc.get("payload") or {}
    if event_type == "invoice_seen":
        return f"factura registrada · {str(payload.get('sha256', ''))[:8]}"
    if event_type == "decision":
        return f"decisión → {payload.get('result', '?')} · {payload.get('total_ms', 0)}ms"
    if event_type == "feature":
        return (
            f"p{payload.get('page')} · {payload.get('stage', '?')} · "
            f"{payload.get('outcome', '?')} · {payload.get('latency_ms', 0)}ms"
        )
    if event_type == "fields":
        return f"campos · {payload.get('parser_ms', 0)}ms"
    if event_type == "override":
        return (
            f"{payload.get('field_type', '?')}: {_short(payload.get('before'))} → "
            f"{_short(payload.get('after'))} · {payload.get('who', '?')}"
        )
    if event_type == "item_error":
        return f"error: {payload.get('error', '?')}"
    return event_type


def logs(
    store: PouchStore,
    invoice: str = "",
    q: str = "",
    event_type: str = "",
    limit: int = 200,
    offset: int = 0,
) -> dict:
    docs = store.for_file(invoice, "event") if invoice else store.list("event:")
    docs = sorted(
        (store.hydrate(d) for d in docs), key=lambda d: (d["timestamp"], d["_id"]), reverse=True
    )
    types = sorted({d["type"] for d in docs})
    items = []
    for d in docs:
        if event_type and event_type != d["type"]:
            continue
        summary = _log_summary(d)
        if q and q.casefold() not in summary.casefold():
            continue
        items.append(
            {
                "seq": d["_id"],
                "ts": d["timestamp"],
                "type": d["type"],
                "invoice_id": d["file_key"],
                "file_id": d["file_id"],
                "decision_id": f"decision:{d['scan_id']}" if d["type"] == "decision" else None,
                "summary": summary,
                "payload": d.get("payload"),
            }
        )
    return {"total": len(items), "types": types, "items": items[offset : offset + limit]}


def write_override(
    store: PouchStore, key: str, scan_id: str, payload: dict, doc_id: str | None = None
) -> str:
    """Append an override event for a scan; returns its document id.

    A caller may supply a deterministic ``doc_id`` (review transaction + field)
    so a retried resolution never duplicates the override.
    """
    scan = store.get(f"scan:{key}:{scan_id}")
    if scan is None:
        raise KeyError(scan_id)
    doc_id = doc_id or f"event:{scan_id}:{uuid.uuid4()}"
    if store.get(doc_id) is not None:
        return doc_id
    store.put(
        {
            "_id": doc_id,
            "kind": "event",
            **{k: scan[k] for k in ("file_id", "file_key", "invoice_id", "scan_id")},
            "type": "override",
            "payload": payload,
            "timestamp": time.time(),
        }
    )
    return doc_id


def archive_output(root: Path, scan_id: str, path: Path, media_type: str) -> None:
    store = PouchStore(root)
    if not scan_id:
        return
    decision = store.get(f"decision:{scan_id}")
    if decision is None:
        raise RuntimeError(f"Missing PouchDB decision for scan {scan_id}")
    identity = {k: decision[k] for k in ("file_id", "file_key", "invoice_id", "scan_id")}
    store.artifact(identity, "report", path.name, path, media_type)
