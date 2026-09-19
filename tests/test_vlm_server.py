"""Integration tests for the Filemaid local VLM server."""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI, Request

from filemaid.server import create_server


class DummyConfig:
    def __init__(self, root: Path) -> None:
        self.root = root


class ReadyProvisioner:
    """Injected dependency: the local VLM is ready (no real download/start)."""

    def ensure(self, wait: bool = False) -> dict:
        return self.status()

    def status(self) -> dict:
        return {
            "state": "ready",
            "downloaded": True,
            "running": True,
            "ready": True,
            "detail": "",
            "error": "",
            "model": "",
            "mmproj": "",
            "binary": None,
        }


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


class NotReadyProvisioner:
    def ensure(self, wait: bool = False) -> dict:
        return self.status()

    def status(self) -> dict:
        return {
            "state": "error",
            "downloaded": False,
            "running": False,
            "ready": False,
            "detail": "",
            "error": "weights incomplete",
            "model": "",
            "mmproj": "",
            "binary": None,
        }


def test_server_refuses_to_start_without_local_vlm(tmp_path):
    app = create_server(DummyConfig(tmp_path / "server_data"), provisioner=NotReadyProvisioner())
    port = _find_free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical")
    server = uvicorn.Server(config)

    def _run() -> None:
        try:
            server.run()
        except SystemExit:
            pass  # uvicorn exits nonzero when lifespan startup fails

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(timeout=5)
    assert not server.started


class FlakyProvisioner:
    """Ready at startup, then reports not-ready (sidecar stopped/crashed)."""

    def __init__(self) -> None:
        self.ready = True

    def ensure(self, wait: bool = False) -> dict:
        return self.status()

    def status(self) -> dict:
        return {
            "state": "ready" if self.ready else "idle",
            "downloaded": True,
            "running": self.ready,
            "ready": self.ready,
            "detail": "",
            "error": "",
            "model": "",
            "mmproj": "",
            "binary": None,
        }


def test_healthz_reflects_stopped_sidecar(tmp_path):
    provisioner = FlakyProvisioner()
    app = create_server(DummyConfig(tmp_path / "server_data"), provisioner=provisioner)
    port = _find_free_port()
    server_obj, thread = _run_server_in_thread(app, port)

    try:
        base = f"http://127.0.0.1:{port}"
        assert httpx.get(f"{base}/healthz").json()["vlm_ready"] is True
        provisioner.ready = False  # sidecar stopped after startup
        assert httpx.get(f"{base}/healthz").json()["vlm_ready"] is False
    finally:
        _stop_server_and_join(server_obj, thread)


def test_server_auth_and_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "my-secret-key")
    server_dir = tmp_path / "server_data"
    app = create_server(DummyConfig(server_dir), provisioner=ReadyProvisioner())
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
    app = create_server(DummyConfig(server_dir), provisioner=ReadyProvisioner())
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


def test_vlm_forwards_to_local_sidecar(tmp_path, monkeypatch):
    # A real local HTTP sidecar stub (not a mock echo): exercises the forward path.
    sidecar = FastAPI()

    @sidecar.post("/v1/chat/completions")
    async def handler(request: Request):
        data = await request.json()
        assert data["messages"][0]["content"] == "OCR:"
        return {"choices": [{"message": {"role": "assistant", "content": "TOTAL 123.45 EUR"}}]}

    sidecar_port = _find_free_port()
    sidecar_server, sidecar_thread = _run_server_in_thread(sidecar, sidecar_port)

    class _Manager:
        base_url = f"http://127.0.0.1:{sidecar_port}"

        def ensure_started(self, wait_s: float = 0) -> bool:
            return True

        def touch(self) -> None:
            pass

    monkeypatch.setattr("filemaid.server.get_manager", lambda cfg=None: _Manager())
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "client-token")
    app = create_server(DummyConfig(tmp_path / "server_data"), provisioner=ReadyProvisioner())
    server_port = _find_free_port()
    server_obj, server_thread = _run_server_in_thread(app, server_port)

    try:
        base = f"http://127.0.0.1:{server_port}"
        resp = httpx.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": "Bearer client-token"},
            json={"messages": [{"role": "user", "content": "OCR:"}]},
            timeout=10.0,
        )
        assert resp.status_code == 200
        assert resp.json()["choices"][0]["message"]["content"] == "TOTAL 123.45 EUR"
    finally:
        _stop_server_and_join(server_obj, server_thread)
        _stop_server_and_join(sidecar_server, sidecar_thread)


def test_vlm_unavailable_returns_503(tmp_path, monkeypatch):
    class _DownManager:
        base_url = "http://127.0.0.1:9"

        def ensure_started(self, wait_s: float = 0) -> bool:
            return False

        def touch(self) -> None:
            pass

    monkeypatch.setattr("filemaid.server.get_manager", lambda cfg=None: _DownManager())
    monkeypatch.setenv("FILEMAID_SERVER_TOKEN", "client-token")
    app = create_server(DummyConfig(tmp_path / "server_data"), provisioner=ReadyProvisioner())
    port = _find_free_port()
    server_obj, thread = _run_server_in_thread(app, port)

    try:
        resp = httpx.post(
            f"http://127.0.0.1:{port}/v1/chat/completions",
            headers={"Authorization": "Bearer client-token"},
            json={"messages": [{"role": "user", "content": "OCR:"}]},
            timeout=10.0,
        )
        assert resp.status_code == 503
    finally:
        _stop_server_and_join(server_obj, thread)
