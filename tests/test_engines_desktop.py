"""Ventana nativa pywebview: backend de ventana, arranque y puente de vigilancia.

La ventana nativa no se abre en tests (degrada a navegador, extra desktop). El
puente de vigilancia se prueba a fondo en `test_desktop_watcher.py`; aquí solo
se comprueba la superficie que expone `Api`.
"""

from __future__ import annotations

import os
import sys

import pytest

from filemaid.desktop.app import Api, _gui_backend, _Runtime, _StderrArranque, ui_destino


def test_api_ping_vivo(cfg):
    assert Api(cfg).ping() == "pong"


def test_api_expone_el_puente_de_vigilancia(cfg):
    api = Api(cfg)
    estado = api.vigilancia_estado()
    assert set(estado) == {
        "enabled",
        "folder",
        "running",
        "error",
        "processed",
        "pending",
        "notifications",
    }
    assert estado["enabled"] is False
    assert estado["folder"] == ""
    assert callable(api.elegir_carpeta)
    assert callable(api.vigilancia_configurar)
    assert callable(api.vigilancia_escanear)
    assert callable(api.arrancar_vigilancia)
    api.detener_vigilancia()


def test_gui_backend_qt_en_linux_y_windows_y_auto_en_otras(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "qtpy", object())
    assert _gui_backend() == "qt"

    monkeypatch.setattr(sys, "platform", "win32")
    assert _gui_backend() == "qt"

    monkeypatch.setitem(sys.modules, "qtpy", None)
    assert _gui_backend() is None

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "qtpy", object())
    assert _gui_backend() is None


def test_stderr_arranque_sin_fd2_degrada(monkeypatch):
    def _sin_fd(_fd):
        raise OSError("fd 2 no válido")

    monkeypatch.setattr(os, "dup", _sin_fd)
    arranque = _StderrArranque()
    with arranque:
        arranque.restaurar()
    assert arranque.texto() == ""


def test_stderr_arranque_captura_sondas_y_restaura(tmp_path):
    destino = tmp_path / "err.txt"
    viejo = os.dup(2)
    f = os.open(destino, os.O_WRONLY | os.O_CREAT)
    os.dup2(f, 2)
    try:
        arranque = _StderrArranque()
        with arranque:
            os.write(2, b"vkDebug: sonda del sistema")
            arranque.restaurar()
            os.write(2, b"post-carga")
    finally:
        os.dup2(viejo, 2)
        os.close(viejo)
        os.close(f)
    # la sonda queda capturada; tras restaurar, stderr fluye normal
    assert "vkDebug" in arranque.texto()
    assert destino.read_text() == "post-carga"


def test_ui_destino_url_de_dev_tiene_prioridad(monkeypatch, tmp_path):
    monkeypatch.delenv("FILEMAID_UI_URL", raising=False)
    dist_inexistente = tmp_path / "no-existe" / "index.html"
    monkeypatch.setattr("filemaid.desktop.app._dist_index", lambda: dist_inexistente)
    with pytest.raises(SystemExit):
        ui_destino(_Runtime())  # sin dist y sin URL: instrucción clara

    monkeypatch.setenv("FILEMAID_UI_URL", "http://127.0.0.1:5173")
    assert ui_destino(_Runtime()) == "http://127.0.0.1:5173"
