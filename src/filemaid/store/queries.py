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

from filemaid.parse.extractors import all_extractors

from .pouch import PouchStore


def _timeline(doc: dict) -> tuple:
    """Order shared by every scan and event projection: time, then document id."""
    return (doc["timestamp"], doc["_id"])


def _group_scans(scans: list[dict]) -> dict[str, list[dict]]:
    """Scans grouped by file key, ordered like ``list(f"scan:{key}:")``."""
    grouped: dict[str, list[dict]] = {}
    for scan in scans:
        grouped.setdefault(scan["_id"][len("scan:") :].split(":", 1)[0], []).append(scan)
    for group in grouped.values():
        group.sort(key=_timeline)
    return grouped


def scans_for(store: PouchStore, key: str) -> list[dict]:
    return sorted(store.list(f"scan:{key}:"), key=_timeline)


def _decisions_for_scans(store: PouchStore, scans: list[dict]) -> list[dict]:
    """Hydrated decisions of ``scans``, in scan order; scans without one are skipped."""
    ids = [f"decision:{s['scan_id']}" for s in scans]
    return store.hydrate_many(
        [d for d in store.batch([{"op": "get", "id": i} for i in ids]) if d is not None]
    )


def decisions_for(store: PouchStore, key: str) -> list[dict]:
    return _decisions_for_scans(store, scans_for(store, key))


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
    return store.hydrate_many(store.list(f"feature:{scan_id}:"))


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


def _covering_resolution(resolutions: list[dict], decision_id: str) -> dict | None:
    """The newest resolution that covers ``decision_id``, if any."""
    for r in reversed(resolutions):
        if decision_id in {r.get("resolved_decision_id"), r.get("reviewed_decision_id")}:
            return r
    return None


def resolution_for(store: PouchStore, key: str) -> dict | None:
    """The resolution that covers the invoice's latest decision, if any."""
    decisions = decisions_for(store, key)
    latest = decisions[-1] if decisions else None
    if latest is None:
        return None
    return _covering_resolution(resolutions_for(store, key), latest["_id"])


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

# Field types a human can confirm, discard or override. Same source as
# ``review.SUPPORTED_FIELDS`` (one catalogue, derived from the extractors).
SUPPORTED_FIELDS: tuple[str, ...] = tuple(sorted({name for name, _, _ in all_extractors()}))


def _field_status(candidates: list[dict], override: dict | None) -> dict:
    """Per-field marker for the review UI: has a reading, discarded, or neither.

    ``discarded`` is the newest committed override with ``after: null`` — the
    human removed the reading. ``has_value`` is about candidates, so a field that
    was never extracted and one that was discarded are told apart by the marker
    while both stay override-able.
    """
    payload = (override or {}).get("payload") or {}
    return {
        "has_value": bool(candidates),
        "discarded": override is not None and payload.get("after") is None,
        "candidates": len(candidates),
        "last_override": (
            None
            if override is None
            else {
                "id": override["_id"],
                "field_type": payload.get("field_type"),
                "before": payload.get("before"),
                "after": payload.get("after"),
                "who": payload.get("who", ""),
                "reason": payload.get("reason", ""),
                "timestamp": override.get("timestamp"),
            }
        ),
    }


def _invoice_row(file: dict, scans: list[dict], decisions: list[dict], state: str) -> dict:
    """One dashboard row; ``decisions`` are the file's hydrated decisions in order."""
    latest = decisions[-1] if decisions else None
    source = scans[-1].get("source_path")
    return {
        "id": file["file_key"],
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


def invoice_rows(store: PouchStore) -> list[dict]:
    selection, files, scans, decisions = store.batch(
        [
            {"op": "selection"},
            {"op": "list", "prefix": "file:"},
            {"op": "list", "prefix": "scan:"},
            {"op": "list", "prefix": "decision:"},
        ]
    )
    states = selection["states"]
    by_id = {d["_id"]: d for d in decisions}
    grouped = _group_scans(scans)
    invoices: list[tuple[dict, list[dict], list[dict]]] = []
    for file in files:
        file_scans = grouped.get(file["file_key"], [])
        if not file_scans:
            continue
        ids = [f"decision:{s['scan_id']}" for s in file_scans]
        invoices.append((file, file_scans, [by_id[i] for i in ids if i in by_id]))
    hydrated = {
        d["_id"]: d
        for d in store.hydrate_many(
            [d for _, _, file_decisions in invoices for d in file_decisions]
        )
    }
    rows = [
        _invoice_row(
            file,
            file_scans,
            [hydrated[d["_id"]] for d in file_decisions],
            states.get(file["file_key"], "pending"),
        )
        for file, file_scans, file_decisions in invoices
    ]
    return sorted(rows, key=lambda r: (r["file_id"], r["id"]))


def invoice_detail(store: PouchStore, key: str) -> dict | None:
    selection, file, scans, resolutions = store.batch(
        [
            {"op": "selection"},
            {"op": "get", "id": f"file:{key}"},
            {"op": "list", "prefix": f"scan:{key}:"},
            {"op": "list", "prefix": f"resolution:{key}:"},
        ]
    )
    if file is None:
        return None
    scans = sorted(scans, key=_timeline)
    if not scans:
        return None
    resolutions = sorted(resolutions, key=lambda d: (d.get("timestamp", 0), d["_id"]))
    # The fields document belongs to the scan of the latest decision, or to the
    # last scan while the invoice has none; both are known from the raw scan ids,
    # so the second round trip carries everything else.
    fields_by_scan = {}
    requests = [{"op": "query", "index": "by_file", "key": [file["file_id"], "event"]}]
    requests += [{"op": "get", "id": f"decision:{s['scan_id']}"} for s in scans]
    requests += [{"op": "get", "id": f"fields:{s['scan_id']}"} for s in scans]
    events, *rest = store.batch(requests)
    decisions_raw = [d for d in rest[: len(scans)] if d is not None]
    for scan, fields in zip(scans, rest[len(scans) :], strict=True):
        fields_by_scan[scan["scan_id"]] = fields
    latest_scan_id = decisions_raw[-1]["scan_id"] if decisions_raw else None
    scan = next((s for s in scans if s["scan_id"] == latest_scan_id), scans[-1])
    fields_doc = fields_by_scan.get(scan["scan_id"])
    overrides_raw = [d for d in events if d.get("file_key") == key and d.get("type") == "override"]

    group = [*decisions_raw, *overrides_raw] + ([fields_doc] if fields_doc else [])
    hydrated = {d["_id"]: d for d in store.hydrate_many(group)}
    decisions = [hydrated[d["_id"]] for d in decisions_raw]
    latest = decisions[-1] if decisions else None
    state = selection["states"].get(key, "pending")
    resolution = _covering_resolution(resolutions, latest["_id"]) if latest else None
    fields_raw = hydrated[fields_doc["_id"]]["fields"] if fields_doc else []

    # Project to Record<string, Candidate[]> expected by UI. Every field the
    # system can override is present, with an empty candidate list when it has no
    # reading: a field can be discarded ("sin valor") or overridden by hand even
    # when the extraction never produced a candidate.
    fields_map: dict[str, list[dict]] = {f_type: [] for f_type in SUPPORTED_FIELDS}
    for f in fields_raw:
        fields_map[f.get("type", "")] = f.get("values", [])

    overrides = [hydrated[d["_id"]] for d in overrides_raw]
    latest_override: dict[str, dict] = {}
    for d in sorted(overrides, key=_timeline):
        field_type = (d.get("payload") or {}).get("field_type")
        if field_type:
            latest_override[field_type] = d

    field_status = {
        f_type: _field_status(
            fields_map[f_type], latest_override.get(f_type)
        )
        for f_type in SUPPORTED_FIELDS
    }

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
        "supported_fields": list(SUPPORTED_FIELDS),
        "field_status": field_status,
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
    docs = sorted(store.hydrate_many(docs), key=_timeline, reverse=True)
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
