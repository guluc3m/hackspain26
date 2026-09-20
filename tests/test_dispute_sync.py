"""Dispute withholding, review resolution and selective replication.

Unit tests run against the real JS PouchDB engine. The replication tests need an
isolated real CouchDB: set ``FILEMAID_TEST_COUCHDB_URL`` (root URL), plus
``FILEMAID_TEST_COUCHDB_USER`` / ``FILEMAID_TEST_COUCHDB_PASSWORD``.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid

import httpx
import pytest

from filemaid.extract.cache import sha256_file
from filemaid.pipeline import Pipeline, apply_overrides, invoice_id_for
from filemaid.review import list_disputed, resolve_review
from filemaid.rules.config import RuleConfig
from filemaid.rules.escoger import escoger, field_selection
from filemaid.store import queries
from filemaid.store.pouch import PouchStore
from filemaid.store.trace import ScanTrace
from filemaid.types import Candidate, ExtractionField
from test_smoke_pipeline import _make_text_pdf

ESCALAR_TEXT = (
    "FACTURA Suministros Garcia SL TOTAL 121,00 EUR Fecha 15/01/2026 "
    "Base 100,00 EUR IVA 21,00 EUR"
)
PAGAR_TEXT = (
    "FACTURA 2026/001 - Suministros Garcia SL - NIF B12345678 - IBAN ES91 2100 0418 4502 0005 1332"
    " - Pedido P-2026-001 - Fecha: 15/01/2026 - Base: 100,00 EUR - IVA 21% - Cuota IVA: 21,00 EUR"
    " - TOTAL : 121,00 EUR"
)


def _process(cfg, tmp_path, name: str, text: str) -> tuple[PouchStore, str, str]:
    source = tmp_path / name
    _make_text_pdf(source, text)
    Pipeline(cfg).process_pdf(source)
    store = PouchStore(cfg.root)
    row = next(r for r in queries.invoice_rows(store) if r["file_id"] == name)
    return store, row["id"], row["decision_id"]


# ---------------------------------------------------------------- overrides


def test_apply_overrides_uses_latest_per_field_and_keeps_originals():
    fields = [ExtractionField(type="total", values=[Candidate("pypdf", "100", 0.9)])]
    overrides = [
        {"_id": "event:1", "timestamp": 1.0, "payload": {"field_type": "total", "after": "110", "who": "a"}},
        {"_id": "event:2", "timestamp": 2.0, "payload": {"field_type": "total", "after": "120", "who": "b"}},
    ]
    effective, applied = apply_overrides(fields, overrides)
    assert [a["value"] for a in applied] == ["120"]
    assert effective[0].values[0].extractor == "override"
    assert effective[0].values[0].value == "120"
    assert effective[0].values[1].value == "100"  # original candidate retained


def test_override_wins_score_tie_for_fecha_even_with_equal_confidence(cfg):
    """`fecha` has its own ranking; the override must still win a 1.0 tie."""
    rule_config = RuleConfig.load(cfg.rules_config_path)
    field = ExtractionField(type="fecha", values=[Candidate("pypdf", "15/01/2026", 1.0)])
    field.values.insert(0, Candidate("override", "16/01/2026", 1.0))
    selection = escoger(field, field_selection(rule_config.seleccion, "fecha"))
    assert selection.candidate is not None
    assert selection.candidate.extractor == "override"
    assert selection.candidate.value == "16/01/2026"


def test_override_flows_through_engine_and_is_recorded(cfg, tmp_path):
    store, key, decision_id = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    result = resolve_review(
        store,
        cfg,
        key,
        {
            "who": "alice",
            "reason": "nif corregido",
            "corrected": {"nif": "B12345678"},
            "expected_decision_id": decision_id,
        },
    )
    resolved = store.get(result["decision_id"])
    assert resolved["overrides_applied"][0]["field_type"] == "nif"
    assert resolved["overrides_applied"][0]["value"] == "B12345678"
    nif_rule = next(
        r for r in resolved["decision"]["rule_evaluations"] if r["code"] == "NIF_IN_MASTER"
    )
    assert nif_rule["verdict"] == "PASS"
    assert "override" in nif_rule["chosen_candidates"]["nif"]


# ---------------------------------------------------------------- selection


def test_selection_withholds_escalated_and_releases_on_resolution(cfg, tmp_path):
    store, key, decision_id = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    row = next(r for r in queries.invoice_rows(store) if r["id"] == key)
    assert row["disputed"] is True
    assert row["withheld_from_sync"] is True
    assert row["review_state"] == "pending"
    assert [i["file_key"] for i in list_disputed(store)] == [key]

    selection = store.selection()
    assert key in selection["withheld_file_keys"]
    assert selection["states"][key] == "pending"
    for doc in store.for_file("esc.pdf"):
        assert doc["_id"] in selection["doc_ids"], doc["_id"]

    result = resolve_review(
        store,
        cfg,
        key,
        {"who": "alice", "reason": "revisado", "expected_decision_id": decision_id},
    )
    assert result["review_state"] == "resolved"
    assert result["disputed"] is False
    selection = store.selection()
    assert key not in selection["withheld_file_keys"]
    assert selection["states"][key] == "resolved"
    assert list_disputed(store) == []


def test_selection_withholds_newer_scan_even_after_pagar(cfg, tmp_path):
    store, key, _ = _process(cfg, tmp_path, "ok.pdf", PAGAR_TEXT)
    assert store.selection()["states"][key] == "not_required"
    # An in-progress reprocess adds a newer scan without a decision.
    source = tmp_path / "ok.pdf"
    sha = sha256_file(source)
    trace = ScanTrace(store, source, sha, invoice_id_for(sha))
    trace.begin("r", "e", "m")
    assert store.selection()["states"][key] == "pending"
    assert key in store.selection()["withheld_file_keys"]


def test_selection_withholds_offloaded_decision_result(cfg, tmp_path):
    """An offloaded decision keeps its result at the top level (routing metadata)."""
    store = PouchStore(cfg.root)
    store.put(
        {
            "_id": "file:k1",
            "kind": "file",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "sha256": "s",
        }
    )
    store.put(
        {
            "_id": "scan:k1:s1",
            "kind": "scan",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "scan_id": "s1",
            "timestamp": 1.0,
        }
    )
    store.put(
        {
            "_id": "artifact:s1:offloaded",
            "kind": "artifact",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "scan_id": "s1",
            "stage": "decision",
            "chunks": [],
            "timestamp": 1.5,
        }
    )
    store.put(
        {
            "_id": "decision:s1",
            "kind": "decision",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "scan_id": "s1",
            "timestamp": 2.0,
            "result": "PAGAR",
            "payload_ref": "artifact:s1:offloaded",
        }
    )
    assert store.selection()["states"]["k1"] == "not_required"


def test_selection_withholds_job_envelope_until_inputs_eligible(cfg, tmp_path):
    store = PouchStore(cfg.root)
    store.put(
        {
            "_id": "job:j1",
            "kind": "job",
            "origin": "upload",
            "expected": [{"file_id": "a.pdf", "sha256": "deadbeef"}],
            "created_at": 1.0,
        }
    )
    store.put({"_id": "job_event:j1:e1", "kind": "job_event", "job_id": "j1", "type": "job_started"})
    store.put({"_id": "job_result:j1", "kind": "job_result", "job_id": "j1", "status": "complete"})
    store.put({"_id": "job_item:j1:k1", "kind": "job_item", "job_id": "j1", "file_key": "k1"})
    selection = store.selection()
    for doc_id in ("job:j1", "job_event:j1:e1", "job_result:j1", "job_item:j1:k1"):
        assert doc_id in selection["doc_ids"], doc_id


def test_selection_withholds_orphan_blob_and_unproven_cache(cfg, tmp_path):
    store = PouchStore(cfg.root)
    digest = hashlib.sha256(b"orphan").hexdigest()
    store.request(op="blob", sha256=digest, data=base64.b64encode(b"orphan").decode("ascii"))
    store.put(
        {
            "_id": "cache:abc",
            "kind": "cache",
            "key": "abc",
            "page_sha256": "p1",
            "extractor_version": "v",
            "config_version": "c",
        }
    )
    selection = store.selection()
    assert f"blob:{digest}" in selection["blobs"]
    assert "cache:abc" in selection["doc_ids"]


def test_selection_withholds_offloaded_cache_decision_feature_graph(cfg, tmp_path):
    """Offloaded payloads, anonymous cache artifacts and their blobs stay local."""
    store = PouchStore(cfg.root)
    store.put(
        {
            "_id": "file:k1",
            "kind": "file",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "sha256": "s",
        }
    )
    store.put(
        {
            "_id": "scan:k1:s1",
            "kind": "scan",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "scan_id": "s1",
            "timestamp": 1.0,
        }
    )
    # Offloaded feature: no inline sha, so the page owner cannot be proven.
    feature_art = store.artifact(
        {"scan_id": "s1", "file_key": "k1", "invoice_id": "inv"},
        "feature",
        "feature.json",
        b"x" * 10,
        "application/json",
    )
    store.put(
        {
            "_id": "feature:s1:0:vlm:0",
            "kind": "feature",
            "file_id": "a.pdf",
            "file_key": "k1",
            "invoice_id": "inv",
            "scan_id": "s1",
            "stage": "vlm",
            "page": 0,
            "payload_ref": feature_art,
            "timestamp": 1.1,
        }
    )
    # Offloaded cache whose payload artifact carries no file identity.
    cache_art = store.artifact(
        {"scan_id": "cache-abc"}, "cache", "cache.json", b"y" * 10, "application/json"
    )
    store.put(
        {
            "_id": "cache:abc",
            "kind": "cache",
            "key": "abc",
            "page_sha256": "p1",
            "extractor_version": "v",
            "config_version": "c",
            "payload_ref": cache_art,
        }
    )
    # A withheld document offloading to an anonymous artifact withholds it too.
    anonymous_art = store.artifact(
        {"scan_id": "anon"}, "payload", "p.json", b"z" * 10, "application/json"
    )
    store.put(
        {
            "_id": "custom:offloaded",
            "kind": "custom",
            "file_key": "k1",
            "invoice_id": "inv",
            "scan_id": "s1",
            "payload_ref": anonymous_art,
        }
    )

    selection = store.selection()
    for doc_id in ("cache:abc", cache_art, feature_art, anonymous_art):
        assert doc_id in selection["doc_ids"], doc_id
    for doc_id in (cache_art, feature_art, anonymous_art):
        for chunk in store.get(doc_id)["chunks"]:
            assert chunk in selection["blobs"], chunk


def test_selection_keeps_unrelated_dynamic_docs(cfg, tmp_path):
    store = PouchStore(cfg.root)
    store.put({"_id": "custom:dynamic", "kind": "future-schema", "unknown": {"ñ": [1, 2]}})
    selection = store.selection()
    assert "custom:dynamic" not in selection["doc_ids"]
    assert selection["withheld_file_keys"] == []


# ---------------------------------------------------------------- resolution


def test_resolve_review_requires_identity_and_reason(cfg, tmp_path):
    store, key, decision_id = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    with pytest.raises(ValueError):
        resolve_review(store, cfg, key, {"who": "a", "reason": "x"})
    with pytest.raises(ValueError):
        resolve_review(store, cfg, key, {"who": "", "reason": "x", "expected_decision_id": decision_id})
    with pytest.raises(ValueError):
        resolve_review(store, cfg, key, {"who": "a", "reason": "", "expected_decision_id": decision_id})
    with pytest.raises(RuntimeError):
        resolve_review(
            store, cfg, key, {"who": "a", "reason": "x", "expected_decision_id": "decision:other"}
        )
    with pytest.raises(ValueError):
        resolve_review(
            store, cfg, key, {"who": "a", "reason": "x", "accepted": ["nope"], "expected_decision_id": decision_id}
        )
    with pytest.raises(ValueError):
        resolve_review(
            store,
            cfg,
            key,
            {
                "who": "a",
                "reason": "x",
                "accepted": ["nif"],
                "corrected": {"nif": "B12345678"},
                "expected_decision_id": decision_id,
            },
        )


def test_resolve_review_rejects_non_escalated(cfg, tmp_path):
    store, key, decision_id = _process(cfg, tmp_path, "ok.pdf", PAGAR_TEXT)
    with pytest.raises(ValueError):
        resolve_review(store, cfg, key, {"who": "a", "reason": "x", "expected_decision_id": decision_id})


def test_resolve_review_is_idempotent_and_conflicts_fail_closed(cfg, tmp_path):
    store, key, decision_id = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    body = {"who": "alice", "reason": "revisado", "expected_decision_id": decision_id}
    first = resolve_review(store, cfg, key, body)
    again = resolve_review(store, cfg, key, body)
    assert again["resolution_id"] == first["resolution_id"]
    assert again["decision_id"] == first["decision_id"]
    # A different resolution of the same reviewed decision must not win silently.
    with pytest.raises(RuntimeError):
        resolve_review(
            store,
            cfg,
            key,
            {"who": "bob", "reason": "otra", "expected_decision_id": decision_id},
        )


def test_resolve_review_resumes_after_crash_before_commit(cfg, tmp_path, monkeypatch):
    store, key, decision_id = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    real_put_conditional = PouchStore.put_conditional

    def failing_put_conditional(self, doc, file_key, expected_decision_id):
        if doc.get("kind") == "resolution":
            raise RuntimeError("crash before commit")
        return real_put_conditional(self, doc, file_key, expected_decision_id)

    monkeypatch.setattr(PouchStore, "put_conditional", failing_put_conditional)
    body = {"who": "alice", "reason": "revisado", "expected_decision_id": decision_id}
    with pytest.raises(RuntimeError):
        resolve_review(store, cfg, key, body)
    monkeypatch.setattr(PouchStore, "put_conditional", real_put_conditional)
    # The recompute happened but the commit did not: the invoice stays withheld.
    assert store.selection()["states"][key] == "pending"
    assert store.get(f"review:{key}:{decision_id.removeprefix('decision:')}") is not None
    result = resolve_review(store, cfg, key, body)
    assert result["review_state"] == "resolved"
    assert store.selection()["states"][key] == "resolved"
    # The retry reused the same transaction and did not duplicate overrides.
    assert len(store.list("event:override:")) == 0


# ---------------------------------------------------------------- real CouchDB


@pytest.fixture
def couchdb(monkeypatch):
    root = os.environ.get("FILEMAID_TEST_COUCHDB_URL")
    if not root:
        pytest.skip("set FILEMAID_TEST_COUCHDB_URL to run real CouchDB integration")
    user = os.environ.get("FILEMAID_TEST_COUCHDB_USER", "")
    password = os.environ.get("FILEMAID_TEST_COUCHDB_PASSWORD", "")
    monkeypatch.setenv("FILEMAID_COUCHDB_USER", user)
    monkeypatch.setenv("FILEMAID_COUCHDB_PASSWORD", password)
    monkeypatch.delenv("FILEMAID_SYNC_TOKEN", raising=False)
    name = "filemaid-dispute-" + uuid.uuid4().hex
    with httpx.Client(
        base_url=root.rstrip("/") + "/",
        auth=(user, password),
        headers={"Accept": "application/json"},
        timeout=30,
    ) as client:
        assert client.get("").json()["couchdb"] == "Welcome"
        client.put(name).raise_for_status()
        try:
            yield root.rstrip("/") + "/" + name, client, name
        finally:
            response = client.delete(name)
            assert response.status_code in {200, 202, 404}


def test_undisputed_syncs_while_disputed_is_withheld(couchdb, cfg, tmp_path):
    url, remote, name = couchdb
    store, ok_key, _ = _process(cfg, tmp_path, "ok.pdf", PAGAR_TEXT)
    _, esc_key, _ = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    store.sync(url)
    assert remote.get(f"{name}/file:{ok_key}").status_code == 200
    assert remote.get(f"{name}/file:{esc_key}").status_code == 404
    for doc in store.for_file("esc.pdf"):
        assert remote.get(f"{name}/{doc['_id']}").status_code == 404, doc["_id"]


def test_release_after_previous_checkpoint_replicates_withheld_docs(couchdb, cfg, tmp_path):
    """Docs skipped by an earlier checkpoint must replicate once resolved."""
    url, remote, name = couchdb
    store, key, decision_id = _process(cfg, tmp_path, "esc.pdf", ESCALAR_TEXT)
    store.sync(url)
    assert remote.get(f"{name}/file:{key}").status_code == 404
    withheld = [doc["_id"] for doc in store.for_file("esc.pdf")]
    assert withheld
    resolve_review(
        store, cfg, key, {"who": "alice", "reason": "revisado", "expected_decision_id": decision_id}
    )
    store.sync(url)
    assert remote.get(f"{name}/file:{key}").status_code == 200
    for doc_id in withheld:
        assert remote.get(f"{name}/{doc_id}").status_code == 200, doc_id
