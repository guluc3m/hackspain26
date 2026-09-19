"""Integration tests for PouchStore synchronization and Filemaid server."""

from __future__ import annotations

import base64
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, HTTPException, Request

from filemaid.server import create_server
from filemaid.store.pouch import PouchStore


class DummyConfig:
    def __init__(self, root: Path) -> None:
        self.root = root


def _find_free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _run_server_in_thread(app: FastAPI, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started, "server did not start"
    return server, thread


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


def test_sync_bidirectional_roundtrip_and_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "secret-test-token")
    server_dir = tmp_path / "server_data"
    client_dir = tmp_path / "client_data"

    server_store = PouchStore(server_dir)
    client_store = PouchStore(client_dir)

    server_cfg = DummyConfig(server_dir)
    app = create_server(server_cfg)
    port = _find_free_port()
    server_obj, _ = _run_server_in_thread(app, port)

    try:
        remote_url = f"http://127.0.0.1:{port}"
        token = "secret-test-token"

        # 1. Create client side artifact and dynamic documents
        raw_blob = b"Hello from sync client! " * 200
        client_art_id = client_store.artifact(
            {"scan_id": "scan-1", "file_id": "doc.pdf"},
            stage="input",
            name="doc.pdf",
            source=raw_blob,
            media_type="application/pdf",
        )
        dynamic_doc = {
            "_id": "custom:dynamic:1",
            "kind": "custom_schema_invoice",
            "arbitrary_field": {"nested": [1, 2, 3], "flag": True},
            "payload_ref": client_art_id,
            "timestamp": time.time(),
        }
        client_store.put(dynamic_doc)

        # 2. Client sync pushes to server
        res1 = client_store.sync(remote_url, token)
        assert res1["ok"] is True
        assert res1["pushed"] >= 2

        # Verify on server
        assert server_store.get(dynamic_doc["_id"]) is not None
        server_dynamic = server_store.get(dynamic_doc["_id"])
        assert server_dynamic["arbitrary_field"] == {"nested": [1, 2, 3], "flag": True}
        # Server can read client's artifact data
        server_art_content = b"".join(server_store.read_artifact(client_art_id))
        assert server_art_content == raw_blob

        # 3. Server adds its own doc & artifact
        server_blob = b"Server artifact response payload"
        server_art_id = server_store.artifact(
            {"scan_id": "scan-2", "file_id": "server.pdf"},
            stage="report",
            name="report.pdf",
            source=server_blob,
            media_type="application/pdf",
        )
        server_doc = {
            "_id": "report:scan-2",
            "kind": "report",
            "data": "server-generated",
            "payload_ref": server_art_id,
        }
        server_store.put(server_doc)

        # 4. Client pulls from server
        res2 = client_store.sync(remote_url, token)
        assert res2["ok"] is True
        assert res2["pulled"] >= 2

        # Verify client got server doc and artifact
        client_pulled = client_store.get(server_doc["_id"])
        assert client_pulled is not None
        assert client_pulled["data"] == "server-generated"
        assert b"".join(client_store.read_artifact(server_art_id)) == server_blob

        revision = client_store.get(server_doc["_id"])["_rev"]
        client_store.sync(remote_url, token)
        assert client_store.get(server_doc["_id"])["_rev"] == revision

    finally:
        server_obj.should_exit = True


def test_sync_conflict_preserves_error(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "secret-token")
    server_dir = tmp_path / "server_data"
    client_dir = tmp_path / "client_data"

    server_store = PouchStore(server_dir)
    client_store = PouchStore(client_dir)

    # Server already has an immutable document with value A
    server_store.put({"_id": "doc:conflict:1", "kind": "record", "value": "A"})

    # Client has document with same ID but value B
    client_store.put({"_id": "doc:conflict:1", "kind": "record", "value": "B"})

    server_cfg = DummyConfig(server_dir)
    app = create_server(server_cfg)
    port = _find_free_port()
    server_obj, _ = _run_server_in_thread(app, port)

    try:
        remote_url = f"http://127.0.0.1:{port}"
        # Sync push must fail with RuntimeError indicating collision/conflict
        with pytest.raises(RuntimeError, match="conflict|collision"):
            client_store.sync(remote_url, "secret-token")

        # Remote value A must be preserved; not overwritten by client
        assert server_store.get("doc:conflict:1")["value"] == "A"
    finally:
        server_obj.should_exit = True


def test_server_auth_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "my-secret-key")
    server_dir = tmp_path / "server_data"
    app = create_server(DummyConfig(server_dir))
    port = _find_free_port()
    server_obj, _ = _run_server_in_thread(app, port)

    try:
        base = f"http://127.0.0.1:{port}"
        # /healthz is public
        r_health = httpx.get(f"{base}/healthz")
        assert r_health.status_code == 200

        # /sync/pull without token -> 401
        r_unauth = httpx.get(f"{base}/sync/pull")
        assert r_unauth.status_code == 401

        # /sync/pull with wrong token -> 401
        r_wrong = httpx.get(f"{base}/sync/pull", headers={"Authorization": "Bearer bad-token"})
        assert r_wrong.status_code == 401

        # With correct token -> 200
        r_ok = httpx.get(f"{base}/sync/pull", headers={"Authorization": "Bearer my-secret-key"})
        assert r_ok.status_code == 200
    finally:
        server_obj.should_exit = True


def test_vlm_forwarding_and_error_scrubbing(tmp_path, monkeypatch):
    # Set up mock upstream VLM server
    mock_upstream_app = FastAPI()

    @mock_upstream_app.post("/v1/chat/completions")
    async def mock_vlm(request: Request):
        auth = request.headers.get("Authorization", "")
        if auth != "Bearer secret-upstream-key":
            raise HTTPException(status_code=401, detail="Unauthorized upstream")
        data = await request.json()
        assert data["messages"][0]["content"] == "OCR:"
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "TOTAL 123.45 EUR",
                    }
                }
            ]
        }

    upstream_port = _find_free_port()
    upstream_server, upstream_thread = _run_server_in_thread(mock_upstream_app, upstream_port)

    # Configure Filemaid server pointing to upstream
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "client-token")
    monkeypatch.setenv("FILEMAID_SERVER_VLM_URL", f"http://127.0.0.1:{upstream_port}/v1")
    monkeypatch.setenv("FILEMAID_SERVER_VLM_KEY", "secret-upstream-key")

    server_dir = tmp_path / "server_data"
    app = create_server(DummyConfig(server_dir))
    server_port = _find_free_port()
    server_obj, _ = _run_server_in_thread(app, server_port)

    try:
        base = f"http://127.0.0.1:{server_port}"
        # 1. Forward request through server to upstream VLM
        resp = httpx.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": "Bearer client-token"},
            json={
                "messages": [{"role": "user", "content": "OCR:"}],
            },
            timeout=10.0,
        )
        assert resp.status_code == 200
        res_data = resp.json()
        assert res_data["choices"][0]["message"]["content"] == "TOTAL 123.45 EUR"

        # 2. Test error scrubbing: upstream down
        upstream_server.should_exit = True
        upstream_thread.join(timeout=5)

        err_resp = httpx.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": "Bearer client-token"},
            json={"messages": []},
            timeout=10.0,
        )
        assert err_resp.status_code == 502
        # Ensure upstream key is not leaked in error detail
        assert "secret-upstream-key" not in err_resp.text
    finally:
        server_obj.should_exit = True


def test_sync_document_endpoint_with_attachments(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "test-token")
    server_dir = tmp_path / "server_data"
    server_store = PouchStore(server_dir)

    # Create document with embedded attachment
    att_data = b"Inline attachment payload"
    doc_id = "doc:with:att"
    server_store.put(
        {
            "_id": doc_id,
            "kind": "custom_record",
            "title": "Embedded test",
            "_attachments": {
                "report.txt": {
                    "content_type": "text/plain",
                    "data": base64.b64encode(att_data).decode("ascii"),
                }
            },
        }
    )

    server_cfg = DummyConfig(server_dir)
    app = create_server(server_cfg)
    port = _find_free_port()
    server_obj, _ = _run_server_in_thread(app, port)

    try:
        base = f"http://127.0.0.1:{port}"
        headers = {"Authorization": "Bearer test-token"}

        # 404 for nonexistent document
        r_missing = httpx.get(f"{base}/sync/document?id=nonexistent", headers=headers)
        assert r_missing.status_code == 404

        # 200 for existing document with attachment data
        r_doc = httpx.get(f"{base}/sync/document?id={doc_id}", headers=headers)
        assert r_doc.status_code == 200
        doc = r_doc.json()
        assert doc["_id"] == doc_id
        assert doc["title"] == "Embedded test"
        assert "report.txt" in doc.get("_attachments", {})
        att_b64 = doc["_attachments"]["report.txt"]["data"]
        assert base64.b64decode(att_b64) == att_data
    finally:
        server_obj.should_exit = True
