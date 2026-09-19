from __future__ import annotations

from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.runtime import RuntimeSettings
from filemaid.store.pouch import PouchStore


def test_settings_survive_restart_without_entering_replicated_documents(cfg):
    settings = RuntimeSettings(cfg)
    chosen = {
        "mode": "standalone",
        "sync_url": "",
        "vlm_url": "http://127.0.0.1:9009/v1",
        "vlm_model": "local-model",
    }
    settings.save(chosen)
    assert RuntimeSettings(cfg).get() == chosen
    assert PouchStore(cfg.root).list("") == []
    config = cfg.extraction_config()
    assert config["vlm_base_url"] == chosen["vlm_url"]
    previous = config["config_version"]
    settings.save({**chosen, "vlm_model": "another-model"})
    assert cfg.extraction_config()["config_version"] != previous


def test_configuration_rejects_invalid_mode_and_credential_urls(cfg):
    client = TestClient(create_app(cfg))
    for values in (
        {"mode": "other"},
        {"mode": "server", "sync_url": ""},
        {"mode": "standalone", "vlm_url": "file:///etc/passwd"},
        {"mode": "server", "sync_url": "https://user:secret@host"},
    ):
        assert client.put("/api/config", json=values).status_code == 422
    assert client.get("/api/config").json()["mode"] == "standalone"
    assert client.post("/api/sync").status_code == 409


def test_failed_sync_does_not_commit_server_mode(cfg, monkeypatch):
    def failure(self, remote_url, token=""):
        raise RuntimeError("remote unavailable")

    monkeypatch.setattr(PouchStore, "sync", failure)
    client = TestClient(create_app(cfg))
    response = client.put(
        "/api/config", json={"mode": "server", "sync_url": "http://127.0.0.1:65534"}
    )
    assert response.status_code == 502
    assert client.get("/api/config").json()["mode"] == "standalone"
    assert client.get("/api/sync/status").json()["state"] == "error"
