from __future__ import annotations

import time

from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.runtime import RuntimeSettings
from filemaid.store.pouch import PouchStore

_SERVER = {
    "mode": "server",
    "sync_url": "http://127.0.0.1:65533/facturas",
    "vlm_url": "https://vision.example/v1",
    "server_api_key": "k",
}


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def test_saved_server_mode_resumes_sync_without_session_gate(cfg, monkeypatch):
    RuntimeSettings(cfg).save(_SERVER)
    calls: list[str] = []

    def sync(self, url, token=""):
        calls.append(url)
        return {"ok": True, "pushed": 0, "pulled": 0, "seq": 1}

    monkeypatch.setattr(PouchStore, "sync", sync)
    with TestClient(create_app(cfg)) as client:
        # Persisted server mode resumes synchronization on startup, no re-confirmation.
        assert _wait_for(lambda: bool(calls))
        assert calls == ["http://127.0.0.1:65533/facturas"]
        assert client.get("/api/config").json()["mode"] == "server"


def test_switching_to_standalone_clears_stale_sync_error(cfg, monkeypatch):
    RuntimeSettings(cfg).save(_SERVER)

    def failure(self, url, token=""):
        raise RuntimeError("remote unavailable")

    monkeypatch.setattr(PouchStore, "sync", failure)
    with TestClient(create_app(cfg)) as client:
        assert _wait_for(lambda: client.get("/api/sync/status").json()["state"] == "error")
        assert client.put("/api/config", json={"mode": "standalone"}).status_code == 200
        status = client.get("/api/sync/status").json()
        assert status["state"] == "standalone"
        assert status["error"] == ""
        assert status["pending"] is False
