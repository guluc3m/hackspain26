"""Integration tests for Filemaid VLM proxy server."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, HTTPException, Request

from filemaid.server import create_server


class DummyConfig:
    def __init__(self, root: Path) -> None:
        self.root = root


def _find_free_port() -> int:
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


def _stop_server_and_join(server_obj: uvicorn.Server, thread: threading.Thread) -> None:
    server_obj.should_exit = True
    thread.join(timeout=5.0)


def test_server_auth_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "my-secret-key")
    server_dir = tmp_path / "server_data"
    app = create_server(DummyConfig(server_dir))
    port = _find_free_port()
    server_obj, thread = _run_server_in_thread(app, port)

    try:
        base = f"http://127.0.0.1:{port}"
        # /healthz is public
        r_health = httpx.get(f"{base}/healthz")
        assert r_health.status_code == 200

        # /v1/chat/completions without token -> 401
        r_unauth = httpx.post(f"{base}/v1/chat/completions", json={"messages": []})
        assert r_unauth.status_code == 401

        # /v1/chat/completions with wrong token -> 401
        r_wrong = httpx.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": "Bearer bad-token"},
            json={"messages": []},
        )
        assert r_wrong.status_code == 401
    finally:
        _stop_server_and_join(server_obj, thread)


def test_former_sync_routes_return_404(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "my-secret-key")
    server_dir = tmp_path / "server_data"
    app = create_server(DummyConfig(server_dir))
    port = _find_free_port()
    server_obj, thread = _run_server_in_thread(app, port)

    try:
        base = f"http://127.0.0.1:{port}"
        auth_headers = {"Authorization": "Bearer my-secret-key"}

        # All former custom sync routes must return 404 even with valid auth
        assert httpx.get(f"{base}/sync/info", headers=auth_headers).status_code == 404
        assert httpx.get(f"{base}/sync/pull", headers=auth_headers).status_code == 404
        assert (
            httpx.post(f"{base}/sync/push", headers=auth_headers, json={"docs": []}).status_code
            == 404
        )
        assert httpx.get(f"{base}/sync/document?id=test", headers=auth_headers).status_code == 404
        dummy_sha = "a" * 64
        assert httpx.get(f"{base}/sync/blob/{dummy_sha}", headers=auth_headers).status_code == 404
        assert (
            httpx.post(
                f"{base}/sync/blob/{dummy_sha}",
                headers=auth_headers,
                content=b"test",
            ).status_code
            == 404
        )
    finally:
        _stop_server_and_join(server_obj, thread)


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
    server_obj, server_thread = _run_server_in_thread(app, server_port)

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
        _stop_server_and_join(upstream_server, upstream_thread)

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
        _stop_server_and_join(server_obj, server_thread)
        _stop_server_and_join(upstream_server, upstream_thread)
