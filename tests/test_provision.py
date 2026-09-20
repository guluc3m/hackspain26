"""Provisioner readiness semantics: truthful state, model verification, manifest failure."""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from filemaid.provision import MODEL_FILES, VlmProvisioner, download_progress


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


def test_download_progress_tracks_bytes_on_disk(tmp_path, monkeypatch):
    """Progress comes from the real .part/final sizes, never invented."""
    files = (("a.gguf", 10, "0" * 64), ("b.mmproj", 6, "1" * 64))
    monkeypatch.setattr("filemaid.provision.MODEL_FILES", files)
    monkeypatch.setattr("filemaid.provision.models_dir", lambda: tmp_path)

    # Nothing observable yet (e.g. llama.cpp binary phase): indeterminate.
    empty = download_progress()
    assert empty["progress"] is None
    assert empty["bytes_done"] == 0
    assert empty["bytes_total"] == 16

    # Partial download: percentage reflects bytes that have actually landed.
    (tmp_path / "a.gguf.part").write_bytes(b"x" * 4)
    partial = download_progress()
    assert partial["progress"] == 0.25
    assert partial["bytes_done"] == 4
    assert partial["file"] == "a.gguf"

    # A lingering .part beats a same-size final file: the helper re-downloads
    # to .part over corrupt weights, so the final copy there is stale.
    (tmp_path / "a.gguf").write_bytes(b"x" * 10)
    assert download_progress()["progress"] == 0.25

    # Both weights complete: done.
    (tmp_path / "a.gguf.part").unlink()
    (tmp_path / "b.mmproj").write_bytes(b"y" * 6)
    assert download_progress()["progress"] == 1.0


def test_status_reports_download_progress(tmp_path, monkeypatch):
    """status() exposes the observed progress while downloading."""
    provisioner = VlmProvisioner(cfg=None)
    monkeypatch.setattr("filemaid.provision.files_ready", lambda: False)
    monkeypatch.setattr(VlmProvisioner, "_sidecar_up", lambda self: False)
    monkeypatch.setattr(
        "filemaid.provision.download_progress",
        lambda: {"progress": 0.5, "bytes_done": 5, "bytes_total": 10, "file": "a.gguf"},
    )
    provisioner._set("downloading", "downloading PaddleOCR-VL Q8 weights + llama.cpp")
    status = provisioner.status()
    assert status["progress"] == 0.5
    assert status["bytes_done"] == 5
    assert status["bytes_total"] == 10
    assert status["file"] == "a.gguf"


def test_model_files_keep_expected_sizes_and_digests():
    """Guard: MODEL_FILES entries are (name, size, sha256) triples."""
    for _name, size, sha in MODEL_FILES:
        assert isinstance(size, int) and size > 0
        assert len(sha) == 64


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
