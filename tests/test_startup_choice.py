from __future__ import annotations

from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.runtime import RuntimeSettings
from filemaid.store.pouch import PouchStore


def test_saved_server_mode_waits_for_startup_choice(cfg, monkeypatch):
    RuntimeSettings(cfg).save({"mode": "server", "sync_url": "http://127.0.0.1:65533/facturas"})
    calls = []

    def sync(self, url, token=""):
        calls.append(url)
        return {"ok": True}

    monkeypatch.setattr(PouchStore, "sync", sync)
    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/config").json()["mode"] == "server"
        assert calls == []
        response = client.put("/api/config", json={"mode": "standalone"})
        assert response.status_code == 200
        assert calls == []
        assert client.get("/api/sync/status").json()["state"] == "standalone"
