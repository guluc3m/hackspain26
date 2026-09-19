from __future__ import annotations

from fastapi.testclient import TestClient

from filemaid.api.app import create_app
from filemaid.runtime import RuntimeSettings
from filemaid.store.pouch import PouchStore


def test_standalone_coerces_remote_endpoints_and_survives_restart(cfg):
    settings = RuntimeSettings(cfg)
    saved = settings.save(
        {
            "mode": "standalone",
            "sync_url": "http://couch.example/facturas",
            "vlm_url": "http://127.0.0.1:9009/v1",
            "vlm_model": "remote-model",
        }
    )
    # Standalone always uses the local VLM: no remote endpoint or model survives.
    assert saved["sync_url"] == ""
    assert saved["vlm_url"] == ""
    assert saved["vlm_model"] == ""
    assert saved["configured"] is True
    assert RuntimeSettings(cfg).get() == {
        "mode": "standalone",
        "sync_url": "",
        "vlm_url": "",
        "vlm_model": "",
        "local_vlm_fallback": False,
        "configured": True,
    }
    # Device-local: never enters the replicated document space.
    assert PouchStore(cfg.root).list("") == []


def test_server_mode_persists_remote_endpoints_and_hashes_config(cfg):
    settings = RuntimeSettings(cfg)
    chosen = {
        "mode": "server",
        "sync_url": "https://couch.example/facturas",
        "vlm_url": "https://vision.example/v1",
        "vlm_model": "remote-model",
        "local_vlm_fallback": True,
    }
    settings.save(chosen)
    got = RuntimeSettings(cfg).get()
    assert got["sync_url"] == chosen["sync_url"]
    assert got["vlm_url"] == chosen["vlm_url"]
    assert got["local_vlm_fallback"] is True
    config = cfg.extraction_config()
    assert config["vlm_base_url"] == chosen["vlm_url"]
    assert config["remote_rungs_enabled"] is True
    previous = config["config_version"]
    settings.save({**chosen, "local_vlm_fallback": False})
    assert cfg.extraction_config()["config_version"] != previous


def test_standalone_disables_remote_rungs_and_uses_local_vlm(cfg):
    RuntimeSettings(cfg).save({"mode": "standalone"})
    config = cfg.extraction_config()
    assert config["vlm_base_url"] == ""
    assert config["remote_rungs_enabled"] is False
    assert config["mode"] == "standalone"


def test_configuration_rejects_invalid_mode_and_credential_urls(cfg):
    client = TestClient(create_app(cfg))
    for values in (
        {"mode": "other"},
        {"mode": "server", "sync_url": ""},
        {
            "mode": "server",
            "sync_url": "https://user:secret@host",
            "vlm_url": "https://vision.example/v1",
        },
        {
            "mode": "server",
            "sync_url": "http://couchdb:5984",
            "vlm_url": "https://vision.example/v1",
        },
        {
            "mode": "server",
            "sync_url": "http://couchdb:5984/_users",
            "vlm_url": "https://vision.example/v1",
        },
        # Server mode requires an explicit remote VLM URL (never derived from CouchDB).
        {"mode": "server", "sync_url": "http://couchdb:5984/facturas"},
        {
            "mode": "server",
            "sync_url": "http://couchdb:5984/facturas",
            "vlm_url": "file:///etc/passwd",
        },
    ):
        assert client.put("/api/config", json=values).status_code == 422
    assert client.get("/api/config").json()["configured"] is False
    assert client.post("/api/sync").status_code == 409


def test_failed_sync_saves_config_and_records_error(cfg, monkeypatch):
    def failure(self, remote_url, token=""):
        raise RuntimeError("remote unavailable")

    monkeypatch.setattr(PouchStore, "sync", failure)
    client = TestClient(create_app(cfg))
    response = client.put(
        "/api/config",
        json={
            "mode": "server",
            "sync_url": "http://127.0.0.1:65534/facturas",
            "vlm_url": "https://vision.example/v1",
        },
    )
    # The configuration is durable even when the remote is offline.
    assert response.status_code == 200
    saved = client.get("/api/config").json()
    assert saved["mode"] == "server"
    assert saved["configured"] is True
    assert saved["sync_url"] == "http://127.0.0.1:65534/facturas"
    # The failure is reported separately, never as a lost configuration.
    assert client.post("/api/sync").status_code == 502
    status = client.get("/api/sync/status").json()
    assert status["ok"] is False
    assert status["state"] == "error"
    assert "remote unavailable" in status["error"]
    assert client.get("/api/config").json()["mode"] == "server"


def test_failed_sync_to_new_destination_reports_pending(cfg, monkeypatch):
    old_url = "http://127.0.0.1:65533/facturas"
    new_url = "http://127.0.0.1:65534/facturas"
    client = TestClient(create_app(cfg))
    client.put(
        "/api/config",
        json={"mode": "server", "sync_url": old_url, "vlm_url": "https://vision.example/v1"},
    )
    # A real successful sync to the OLD destination records its checkpoint.
    seq = PouchStore(cfg.root).request(op="info")["update_seq"]
    monkeypatch.setattr(
        PouchStore,
        "sync",
        lambda self, url, token="": {"ok": True, "pushed": 0, "pulled": 0, "seq": seq},
    )
    assert client.post("/api/sync").status_code == 200
    synced = client.get("/api/sync/status").json()
    assert synced["state"] == "synced"
    assert synced["pending"] is False

    # Point at a NEW destination and fail: it must be pending + error, never synced.
    client.put(
        "/api/config",
        json={"mode": "server", "sync_url": new_url, "vlm_url": "https://vision.example/v1"},
    )

    def failure(self, url, token=""):
        raise RuntimeError("remote unavailable")

    monkeypatch.setattr(PouchStore, "sync", failure)
    assert client.post("/api/sync").status_code == 502
    status = client.get("/api/sync/status").json()
    assert status["state"] == "error"
    assert status["pending"] is True
    assert "remote unavailable" in status["error"]


def test_couchdb_endpoint_never_becomes_vlm_endpoint(cfg):
    settings = RuntimeSettings(cfg)
    settings.save(
        {
            "mode": "server",
            "sync_url": "https://couch.example/facturas",
            "vlm_url": "https://vision.example/v1",
        }
    )
    assert cfg.extraction_config()["vlm_base_url"] == "https://vision.example/v1"
