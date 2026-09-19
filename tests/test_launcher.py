"""Lanzador `start.py`: límites de plataforma y resolución del CLI de Node.

Solo se prueban fronteras inciertas (restricción de plataforma, token
fail-closed, invocación sin shell de npm/npx en Windows, decisión de rebuild de
la UI), no el cableado ni el texto de los mensajes.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_start():
    spec = importlib.util.spec_from_file_location("filemaid_start", REPO_ROOT / "start.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


start = _load_start()


def _no_side_effects(monkeypatch) -> list:
    calls: list = []
    monkeypatch.setattr(start, "_run", lambda *a, **k: calls.append(("run", a)))
    monkeypatch.setattr(start, "_uv_sync", lambda *a, **k: calls.append(("sync", a)))
    monkeypatch.setattr(start, "_ensure_pouchdb", lambda *a, **k: calls.append(("pouchdb", a)))
    return calls


def test_server_rejects_non_linux_before_side_effects(monkeypatch):
    calls = _no_side_effects(monkeypatch)
    monkeypatch.setattr(sys, "platform", "win32")
    with pytest.raises(SystemExit) as exc:
        start.main(["server"])
    assert exc.value.code
    assert calls == []


def test_server_requires_token_for_non_loopback_before_side_effects(monkeypatch):
    calls = _no_side_effects(monkeypatch)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.delenv("FILEMAID_SERVER_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exc:
        start.main(["server", "--host", "0.0.0.0"])
    assert exc.value.code
    assert calls == []


def test_node_cli_prefers_node_cli_js_on_windows(monkeypatch, tmp_path):
    nodejs = tmp_path / "nodejs"
    bin_dir = nodejs / "node_modules" / "npm" / "bin"
    bin_dir.mkdir(parents=True)
    cli = bin_dir / "npm-cli.js"
    cli.write_text("")
    npm = nodejs / "npm.cmd"
    npm.write_text("")
    monkeypatch.setattr(start, "_IS_WINDOWS", True)
    monkeypatch.setattr(start, "_resolve", lambda name: str(npm))
    monkeypatch.setattr(start.shutil, "which", lambda name: r"C:\nodejs\node.exe")
    assert start._node_cli("npm", "ci") == [r"C:\nodejs\node.exe", str(cli), "ci"]


def test_node_cli_errors_without_cli_js_on_windows(monkeypatch, tmp_path):
    npm = tmp_path / "nodejs" / "npm.cmd"
    npm.parent.mkdir(parents=True)
    npm.write_text("")
    monkeypatch.setattr(start, "_IS_WINDOWS", True)
    monkeypatch.setattr(start, "_resolve", lambda name: str(npm))
    monkeypatch.setattr(start.shutil, "which", lambda name: r"C:\nodejs\node.exe")
    with pytest.raises(SystemExit) as exc:
        start._node_cli("npm", "ci")
    assert exc.value.code


def test_node_cli_errors_without_node_on_windows(monkeypatch, tmp_path):
    npm = tmp_path / "nodejs" / "npm.cmd"
    npm.parent.mkdir(parents=True)
    npm.write_text("")
    monkeypatch.setattr(start, "_IS_WINDOWS", True)
    monkeypatch.setattr(start, "_resolve", lambda name: str(npm))
    monkeypatch.setattr(start.shutil, "which", lambda name: None)
    with pytest.raises(SystemExit) as exc:
        start._node_cli("npm", "ci")
    assert exc.value.code


def test_ui_build_skipped_when_dist_newer(monkeypatch, tmp_path):
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    source = frontend / "src" / "main.ts"
    source.write_text("x")
    dist = frontend / "dist"
    dist.mkdir()
    index = dist / "index.html"
    index.write_text("built")
    built = index.stat().st_mtime
    os.utime(source, (built - 100, built - 100))
    monkeypatch.setattr(start, "FRONTEND_DIR", frontend)
    monkeypatch.setattr(start, "DIST_INDEX", index)

    assert start._ui_build_needed() is False

    os.utime(source, (built + 100, built + 100))
    assert start._ui_build_needed() is True


def test_ui_build_needed_without_dist(monkeypatch, tmp_path):
    monkeypatch.setattr(start, "FRONTEND_DIR", tmp_path / "frontend")
    monkeypatch.setattr(start, "DIST_INDEX", tmp_path / "frontend" / "dist" / "index.html")
    assert start._ui_build_needed() is True
