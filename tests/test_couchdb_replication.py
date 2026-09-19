"""Run against an isolated real CouchDB: FILEMAID_TEST_COUCHDB_URL is its root URL."""

from __future__ import annotations

import base64
import os
import uuid

import httpx
import pytest

from filemaid.store.pouch import PouchStore


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
    name = "filemaid-test-" + uuid.uuid4().hex
    with httpx.Client(
        base_url=root.rstrip("/") + "/",
        auth=(user, password),
        headers={"Accept": "application/json"},
        timeout=30,
    ) as client:
        assert client.get("").json()["couchdb"] == "Welcome"
        client.put(name).raise_for_status()
        url = root.rstrip("/") + "/" + name
        try:
            yield url, client, name
        finally:
            response = client.delete(name)
            assert response.status_code in {200, 202, 404}


def test_native_replication_preserves_documents_revisions_attachments_and_checkpoints(
    couchdb, tmp_path
):
    url, remote, name = couchdb
    first = PouchStore(tmp_path / "first")
    second = PouchStore(tmp_path / "second")
    first.local_put("runtime-settings", {"mode": "server", "sync_url": url})
    first.put({"_id": "custom:dynamic", "kind": "future-schema", "unknown": {"ñ": [1, 2]}})
    first.put({"_id": "_design/private", "views": {}})
    payload = b"binary\x00\xff" * 150000
    identity = {
        "scan_id": "scan",
        "file_id": "Factura ñ.PDF",
        "file_key": "key",
        "invoice_id": "invoice",
    }
    artifact_id = first.artifact(identity, "input", identity["file_id"], payload, "application/pdf")
    first.put(
        {"_id": "decision:scan", "kind": "decision", **identity, "decision": {"result": "ESCALAR"}}
    )
    result = first.sync(url)
    assert result["ok"]
    local = first.get("decision:scan")
    assert remote.get(name + "/decision:scan").json()["_rev"] == local["_rev"]
    assert remote.get(name + "/_local/runtime-settings").status_code == 404
    assert remote.get(name + "/_design/private").status_code == 404
    remote.put(name + "/remote:dynamic", json={"other_schema": {"nested": True}}).raise_for_status()
    remote.put(
        name + "/remote:attachment",
        json={
            "_attachments": {
                "raw": {
                    "content_type": "application/octet-stream",
                    "data": base64.b64encode(b"\x00remote\xff").decode(),
                }
            }
        },
    ).raise_for_status()
    second.sync(url)
    assert second.get("custom:dynamic")["unknown"] == {"ñ": [1, 2]}
    assert second.get("remote:dynamic")["other_schema"] == {"nested": True}
    assert b"".join(second.read_artifact(artifact_id)) == payload
    embedded = second.request(op="get_full", id="remote:attachment")
    assert base64.b64decode(embedded["_attachments"]["raw"]["data"]) == b"\x00remote\xff"
    assert second.local_get("runtime-settings") is None
    unchanged = second.sync(url)
    assert unchanged["pushed"] == unchanged["pulled"] == 0
    assert second.get("decision:scan")["_rev"] == local["_rev"]


def test_native_conflicts_are_retained_and_reported(couchdb, tmp_path):
    url, remote, name = couchdb
    local = PouchStore(tmp_path)
    local.put({"_id": "decision:conflict", "kind": "decision", "decision": {"result": "PAGAR"}})
    remote.put(
        name + "/decision:conflict", json={"kind": "decision", "decision": {"result": "ESCALAR"}}
    ).raise_for_status()
    with pytest.raises(RuntimeError, match="conflict"):
        local.sync(url)
    with pytest.raises(RuntimeError, match="conflict"):
        local.get("decision:conflict")
    leaves = remote.get(name + "/decision:conflict", params={"open_revs": "all"}).json()
    assert {leaf["ok"]["decision"]["result"] for leaf in leaves} == {"PAGAR", "ESCALAR"}


def test_denied_document_is_not_reported_as_success(couchdb, tmp_path):
    url, remote, name = couchdb
    remote.put(
        name + "/_design/deny",
        json={
            "validate_doc_update": "function(n,o,u,s){if(n.blocked){throw({forbidden:'denied'})}}"
        },
    ).raise_for_status()
    local = PouchStore(tmp_path)
    local.put({"_id": "blocked", "blocked": True})
    with pytest.raises(RuntimeError, match="replication failed"):
        local.sync(url)
    assert local.get("blocked")["blocked"]
    assert remote.get(name + "/blocked").status_code == 404
    denied = remote.get(name + "/_design/deny").json()
    remote.delete(name + "/_design/deny", params={"rev": denied["_rev"]}).raise_for_status()
    local.sync(url)
    assert remote.get(name + "/blocked").json()["blocked"] is True


def test_missing_database_not_created_and_auth_failure_keeps_local_data(
    couchdb, tmp_path, monkeypatch
):
    url, remote, name = couchdb
    local = PouchStore(tmp_path)
    local.put({"_id": "offline", "value": "retained"})
    with pytest.raises(RuntimeError, match="HTTP 404"):
        local.sync(url + "-missing")
    assert remote.get(name + "-missing").status_code == 404
    monkeypatch.setenv("FILEMAID_COUCHDB_PASSWORD", "wrong-secret")
    monkeypatch.setenv("FILEMAID_COUCHDB_USER", "nonexistent-test-user")
    with pytest.raises(RuntimeError, match="HTTP 401") as error:
        local.sync(url)
    assert "wrong-secret" not in str(error.value)
    assert local.get("offline")["value"] == "retained"


def test_recreated_couchdb_database_recovers_from_local_pouchdb(couchdb, tmp_path):
    url, remote, name = couchdb
    local = PouchStore(tmp_path)
    local.put({"_id": "retained:offline", "kind": "dynamic", "value": "saved"})
    local.sync(url)
    remote.delete(name).raise_for_status()
    remote.put(name).raise_for_status()
    local.sync(url)
    assert remote.get(name + "/retained:offline").json()["value"] == "saved"
