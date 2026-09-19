"""Provisioner readiness semantics: truthful state, model verification, manifest failure."""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from filemaid.provision import VlmProvisioner


def test_error_state_is_never_ready(monkeypatch):
    provisioner = VlmProvisioner(cfg=None)
    provisioner._state = "error"
    provisioner._error = "manifest write failed"
    monkeypatch.setattr("filemaid.provision.files_ready", lambda: True)
    monkeypatch.setattr(VlmProvisioner, "_sidecar_up", lambda self: True)
    status = provisioner.status()
    assert status["state"] == "error"
    assert status["ready"] is False
    assert status["error"] == "manifest write failed"


def test_serves_expected_model_accepts_our_model_and_rejects_foreign(monkeypatch):
    def our_model(url, timeout=0):
        return httpx.Response(
            200,
            json={"data": [{"id": "/models/PaddleOCR-VL-1.6-q8_0.gguf"}]},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx, "get", our_model)
    assert VlmProvisioner._serves_expected_model("http://127.0.0.1:8080")

    def foreign(url, timeout=0):
        return httpx.Response(
            200, json={"data": [{"id": "gpt-4o-mini"}]}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx, "get", foreign)
    assert not VlmProvisioner._serves_expected_model("http://127.0.0.1:8080")


def test_manifest_failure_is_not_ready(tmp_path, monkeypatch):
    """A failed manifest write must surface as error, never as ready."""
    provisioner = VlmProvisioner(SimpleNamespace(root=tmp_path))
    monkeypatch.setattr("filemaid.provision.files_ready", lambda: True)
    monkeypatch.setattr("filemaid.provision.verify_weights", list)
    monkeypatch.setattr("filemaid.provision.binary_path", lambda: "/usr/bin/llama")

    class _Manager:
        base_url = "http://127.0.0.1:8080"

        def ensure_started(self, wait_s: float = 0) -> bool:
            return True

    monkeypatch.setattr("filemaid.llama_manager.get_manager", lambda cfg=None: _Manager())
    monkeypatch.setattr(VlmProvisioner, "_serves_expected_model", staticmethod(lambda url: True))
    monkeypatch.setattr(VlmProvisioner, "_sidecar_up", lambda self: True)

    def boom(self, *args, **kwargs):
        raise RuntimeError("PouchDB unavailable")

    monkeypatch.setattr(VlmProvisioner, "_write_manifest", boom)
    provisioner._run()
    status = provisioner.status()
    assert status["state"] == "error"
    assert status["ready"] is False
    assert "PouchDB unavailable" in status["error"]
