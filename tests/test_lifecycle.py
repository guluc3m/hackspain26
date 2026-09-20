"""Cierre de la app: solo se para lo propio, y cerrar no relanza nada.

Se prueban las fronteras que de verdad pueden romperse al cerrar la ventana:
que un servidor reutilizado nunca se mate, que un cierre definitivo no vuelva a
arrancar el sidecar, que la descarga en curso se corte, y que un cierre fallido
se reporte en vez de tumbar la salida.
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

from filemaid.desktop.app import _ApiServer, _Runtime
from filemaid.llama_manager import LlamaSidecar
from filemaid.processes import terminate_tree
from filemaid.provision import VlmProvisioner


def _sleeping_child() -> subprocess.Popen:
    """Hijo real y longevo, en su propio grupo como los que arranca la app."""
    kwargs = {"start_new_session": True} if os.name == "posix" else {}
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)


def test_stop_terminates_the_sidecar_this_process_started():
    sidecar = LlamaSidecar()
    proc = _sleeping_child()
    sidecar._proc = proc
    assert sidecar.owned is True
    assert sidecar.stop() is True
    assert proc.poll() is not None


def test_stop_never_touches_a_reused_server(monkeypatch):
    """Un sidecar ajeno (otra instancia, otro usuario) se reutiliza, no se mata."""
    killed: list = []
    monkeypatch.setattr(
        "filemaid.llama_manager.terminate_tree", lambda *a, **k: killed.append(a) or True
    )
    sidecar = LlamaSidecar()
    sidecar._external = True
    assert sidecar.stop() is True
    assert killed == []


def test_shutdown_prevents_the_sidecar_from_coming_back(monkeypatch, tmp_path):
    spawned: list = []
    model = tmp_path / "model.gguf"
    mmproj = tmp_path / "model.mmproj"
    model.write_bytes(b"x")
    mmproj.write_bytes(b"x")
    monkeypatch.setattr(LlamaSidecar, "_spawn_locked", lambda self, binary: spawned.append(binary))
    monkeypatch.setattr(LlamaSidecar, "is_up", lambda self: False)
    monkeypatch.setattr("filemaid.llama_manager.shutil.which", lambda name: "/usr/bin/llama")
    sidecar = LlamaSidecar(model=model, mmproj=mmproj)
    assert sidecar.shutdown() is True
    assert sidecar.ensure_started(wait_s=0) is False
    assert spawned == []


def test_provisioner_stop_cuts_the_download_and_blocks_restart(tmp_path, monkeypatch):
    monkeypatch.setattr("filemaid.provision.run_setup", lambda *a, **k: None)
    provisioner = VlmProvisioner(SimpleNamespace(root=tmp_path))
    proc = _sleeping_child()
    provisioner._setup_proc = proc
    assert provisioner.stop() is True
    assert proc.poll() is not None
    provisioner.ensure()
    assert provisioner._thread is None


def test_runtime_close_stops_everything_in_order_and_only_once(monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr(_ApiServer, "stop", lambda self: calls.append("api") or True)
    monkeypatch.setattr(_Runtime, "_stop_provision", lambda self: calls.append("provision") or True)
    monkeypatch.setattr(_Runtime, "_stop_llama", lambda self: calls.append("llama") or True)
    runtime = _Runtime()
    assert runtime.close() == {"api": True, "llama": True, "provision": True}
    assert calls == ["api", "llama", "provision"]
    assert runtime.close() == {}


def test_runtime_close_reports_a_failure_instead_of_raising(monkeypatch, capsys):
    def boom(self) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(_Runtime, "_stop_provision", boom)
    monkeypatch.setattr(_Runtime, "_stop_llama", lambda self: True)
    monkeypatch.setattr(_ApiServer, "stop", lambda self: True)
    results = _Runtime().close()
    assert results["provision"] is False
    assert results["llama"] is True
    assert "provision" in capsys.readouterr().err


def test_terminate_tree_is_safe_on_an_already_exited_child():
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    assert terminate_tree(proc) is True
