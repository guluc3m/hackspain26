"""Human review service: resolve disputed invoices without bypassing the engine.

A resolution is a human act over an escalated invoice. It records the accepted
and/or corrected readings with provenance, recomputes the decision
deterministically (the rules engine still decides), and commits the release.
The payment result is never supplied by the client.

Transaction and crash safety:

* An immutable review marker is written *before* the recompute and an immutable
  resolution commit *after* it. The invoice stays withheld while a marker has no
  commit, so a recompute that yields PAGAR can never be released before the
  resolution is committed.
* The marker persists a transaction token that is also the planned scan id of
  the recompute. A retry of the same intent resumes the same transaction: if the
  recomputed decision exists it is committed, otherwise the recompute is resumed
  (already-written stages are reused). A different intent for the same reviewed
  decision fails closed.
* Before committing, the latest decision must be the recomputed one, so a scan
  ingested concurrently after the expected check cannot be silently resolved.
* Override documents use deterministic ids per transaction and field, so a retry
  never duplicates them.

Concurrency: the marker and commit ids are deterministic, so two different
resolutions of the same decision collide (fail-closed, no arbitrary winner); a
local interprocess lock serialises the common case across CLI/native/web
processes.
"""

from __future__ import annotations

import time
import uuid

from filemaid.config import AppConfig
from filemaid.parse.extractors import all_extractors
from filemaid.pipeline import reprocess_from_store
from filemaid.rules.config import RuleConfig
from filemaid.rules.escoger import escoger, field_selection
from filemaid.store import queries
from filemaid.store.pouch import PouchStore, interprocess_lock
from filemaid.types import Candidate, ExtractionField

SUPPORTED_FIELDS = frozenset(name for name, _, _ in all_extractors())


def _corrections(raw: dict | None) -> dict:
    """Normalised ``corrected`` map; a ``None`` value is the *discard* sentinel.

    ``None`` round-trips verbatim: it is what a reviewer commits to remove a
    reading, so it is never coerced to a string and never dropped from the map
    (the idempotency check compares intents exactly, nulls included).
    """
    return {str(k): v for k, v in sorted((raw or {}).items())}


def _normalize_intent(body: dict) -> dict:
    return {
        "who": str(body.get("who", "")).strip(),
        "reason": str(body.get("reason", "")).strip(),
        "accepted": sorted({str(f) for f in (body.get("accepted") or [])}),
        "corrected": _corrections(body.get("corrected")),
    }


def _intent_of(doc: dict) -> dict:
    return {
        "who": str(doc.get("who", "")).strip(),
        "reason": str(doc.get("reason", "")).strip(),
        "accepted": sorted({str(f) for f in (doc.get("accepted") or [])}),
        "corrected": _corrections(doc.get("corrected")),
    }


def _chosen_candidates(store: PouchStore, scan_id: str, rule_config: RuleConfig) -> dict:
    """The candidate the engine would collapse each field to, for this scan."""
    chosen: dict[str, object] = {}
    for raw in queries.fields_for_scan(store, scan_id):
        field = ExtractionField(
            type=raw.get("type", ""),
            values=[Candidate(**c) for c in raw.get("values", [])],
        )
        selection = escoger(field, field_selection(rule_config.seleccion, field.type))
        if selection.candidate is not None:
            chosen[field.type] = selection.candidate.value
    return chosen


def _latest_decision(store: PouchStore, key: str) -> dict | None:
    decisions = queries.decisions_for(store, key)
    return decisions[-1] if decisions else None


def _pending_reason(latest: dict | None, scans: list[dict]) -> str:
    if not scans:
        return "sin evidencia"
    if latest is None or latest["scan_id"] != scans[-1]["scan_id"]:
        return "procesamiento en curso"
    if latest["decision"]["result"] == "ESCALAR":
        return "escalada pendiente de revisión"
    return "revisión en curso"


def list_disputed(store: PouchStore) -> list[dict]:
    """Invoices withheld from replication, for the review queue."""
    states = store.selection()["states"]
    items = []
    for file in store.list("file:"):
        key = file["file_key"]
        if states.get(key) != "pending":
            continue
        scans = queries.scans_for(store, key)
        latest = _latest_decision(store, key)
        items.append(
            {
                "file_key": key,
                "file_id": file["file_id"],
                "result": latest["decision"]["result"] if latest else None,
                "decision_id": latest["_id"] if latest else None,
                "scan_id": scans[-1]["scan_id"] if scans else None,
                "review_state": "pending",
                "reason": _pending_reason(latest, scans),
                "since": scans[-1]["timestamp"] if scans else None,
            }
        )
    return sorted(items, key=lambda item: (item["file_id"], item["file_key"]))


def review_detail(store: PouchStore, key: str) -> dict | None:
    """Invoice detail plus the dispute/review fields (see queries.invoice_detail)."""
    return queries.invoice_detail(store, key)


def _committed_result(store: PouchStore, commit: dict) -> dict:
    doc = store.get(commit["resolved_decision_id"])
    resolved = store.hydrate(doc) if doc else None
    result = resolved["decision"]["result"] if resolved else None
    return {
        "ok": True,
        "resolution_id": commit["_id"],
        "decision_id": commit["resolved_decision_id"],
        "result": result,
        "review_state": "resolved",
        "disputed": False,
    }


def resolve_review(store: PouchStore, cfg: AppConfig, key: str, body: dict) -> dict:
    """Accept/correct readings, recompute deterministically and commit the release.

    ``corrected`` maps a field type to the value the reviewer declares; ``null``
    means *discard* (the field must end up with no reading at all), which is
    recorded with ``after: None`` and allowed even when the field has no chosen
    candidate and no extracted value. ``accepted`` only confirms readings that
    exist, so it stays validated against ``chosen``.
    """
    intent = _normalize_intent(body)
    expected = str(body.get("expected_decision_id", "")).strip()
    if not expected.startswith("decision:"):
        raise ValueError("expected_decision_id es obligatorio")
    if not intent["who"]:
        raise ValueError("indique quién resuelve la revisión")
    if not intent["accepted"] and not intent["corrected"] and not intent["reason"]:
        raise ValueError("una confirmación sin campos requiere un motivo explícito")
    if set(intent["accepted"]) & set(intent["corrected"]):
        raise ValueError("un campo no puede confirmarse y corregirse a la vez")
    unknown = sorted(
        {f for f in intent["accepted"] + list(intent["corrected"]) if f not in SUPPORTED_FIELDS}
    )
    if unknown:
        raise ValueError(f"campos no soportados: {unknown}")

    file = store.get(f"file:{key}")
    if file is None:
        raise KeyError(key)

    reviewed_scan = expected.removeprefix("decision:")
    marker_id = f"review:{key}:{reviewed_scan}"
    commit_id = f"resolution:{key}:{reviewed_scan}"

    with interprocess_lock(store.root / "review.lock"):
        commit = store.get(commit_id)
        if commit is not None:
            if _intent_of(commit) != intent:
                raise RuntimeError("esta revisión ya se resolvió con otra decisión")
            return _committed_result(store, commit)

        # Validate every accepted field before writing the marker, so a rejected
        # request leaves no marker that would keep the invoice withheld.
        rule_config = RuleConfig.load(cfg.rules_config_path)
        chosen = _chosen_candidates(store, reviewed_scan, rule_config)
        for field_type in intent["accepted"]:
            if field_type not in chosen:
                raise ValueError(f"el campo {field_type} no tiene lectura elegida que confirmar")

        marker = store.get(marker_id)
        if marker is not None:
            if _intent_of(marker) != intent:
                raise RuntimeError("ya hay una resolución en curso distinta para esta factura")
            token = marker["transaction"]
        else:
            latest = _latest_decision(store, key)
            if latest is None or latest["_id"] != expected:
                raise RuntimeError("la decisión cambió; recargue la revisión")
            if latest["decision"]["result"] != "ESCALAR":
                raise ValueError("la factura no está escalada; no hay revisión pendiente")
            token = str(uuid.uuid4())
            store.put_conditional(
                {
                    "_id": marker_id,
                    "kind": "review",
                    "file_key": key,
                    "invoice_id": file.get("invoice_id"),
                    "scan_id": reviewed_scan,
                    "reviewed_decision_id": expected,
                    "transaction": token,
                    **intent,
                    "timestamp": time.time(),
                },
                file_key=key,
                expected_decision_id=expected,
            )

        override_ids: list[str] = []
        for field_type in intent["accepted"]:
            override_ids.append(
                queries.write_override(
                    store,
                    key,
                    reviewed_scan,
                    {
                        "field_type": field_type,
                        "before": chosen[field_type],
                        "after": chosen[field_type],
                        "who": intent["who"],
                        "rung": "review-ui",
                        "reason": intent["reason"] or "confirmación en revisión",
                    },
                    doc_id=f"event:override:{token}:{field_type}",
                )
            )
        for field_type, value in intent["corrected"].items():
            default_reason = (
                "campo descartado en revisión" if value is None else "corrección en revisión"
            )
            override_ids.append(
                queries.write_override(
                    store,
                    key,
                    reviewed_scan,
                    {
                        "field_type": field_type,
                        "before": chosen.get(field_type),
                        "after": value,
                        "who": intent["who"],
                        "rung": "review-ui",
                        "reason": intent["reason"] or default_reason,
                    },
                    doc_id=f"event:override:{token}:{field_type}",
                )
            )

        if store.get(f"decision:{token}") is None:
            reprocess_from_store(store, cfg, file["file_id"], key, scan_id=token, resume=True)

        # Atomic conditional commit: the file's latest decision must still be the
        # recomputed one, so a scan ingested concurrently cannot be resolved by
        # accident.
        store.put_conditional(
            {
                "_id": commit_id,
                "kind": "resolution",
                "file_key": key,
                "invoice_id": file.get("invoice_id"),
                "scan_id": reviewed_scan,
                "reviewed_decision_id": expected,
                "resolved_decision_id": f"decision:{token}",
                "transaction": token,
                "override_ids": override_ids,
                **intent,
                "timestamp": time.time(),
            },
            file_key=key,
            expected_decision_id=f"decision:{token}",
        )

    doc = store.get(f"decision:{token}")
    resolved = store.hydrate(doc) if doc else None
    return {
        "ok": True,
        "resolution_id": commit_id,
        "decision_id": f"decision:{token}",
        "result": resolved["decision"]["result"] if resolved else None,
        "review_state": "resolved",
        "disputed": False,
    }
