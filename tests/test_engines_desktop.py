"""Motores de la arquitectura y puente pywebview: superficie sin definir.

Los contratos existen (signatures); las llamadas lanzan NotImplementedError.
La ventana nativa no se abre en tests (degrada a navegador, extra desktop).
"""

from __future__ import annotations

import os
import sys

import pytest

from filemaid.desktop.app import Api, _gui_backend, _StderrArranque, ui_destino
from filemaid.engines import DecisionEngine, ExtractionEngine
from filemaid.types import ExtractionField


def test_extraction_engine_superficie_sin_definir():
    with pytest.raises(NotImplementedError):
        ExtractionEngine().extraer("factura.pdf")


def test_decision_engine_superficie_sin_definir():
    with pytest.raises(NotImplementedError):
        DecisionEngine().decidir([ExtractionField(type="total")], "inv-1", "f.pdf")


def test_api_ping_vivo():
    assert Api().ping() == "pong"


def test_api_extraer_propaga_llamada_sin_definir():
    with pytest.raises(NotImplementedError):
        Api().extraer("factura.pdf")


def test_api_decidir_propaga_llamada_sin_definir():
    with pytest.raises(NotImplementedError):
        Api().decidir("inv-1")


def test_gui_backend_qt_en_linux_y_auto_en_otras(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "qtpy", object())
    assert _gui_backend() == "qt"

    monkeypatch.setitem(sys.modules, "qtpy", None)
    assert _gui_backend() is None

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setitem(sys.modules, "qtpy", object())
    assert _gui_backend() is None


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
    monkeypatch.delenv("ALBERTITOS_UI_URL", raising=False)
    dist_inexistente = tmp_path / "no-existe" / "index.html"
    monkeypatch.setattr("filemaid.desktop.app._dist_index", lambda: dist_inexistente)
    with pytest.raises(SystemExit):
        ui_destino()  # sin dist y sin URL: instrucción clara

    monkeypatch.setenv("ALBERTITOS_UI_URL", "http://127.0.0.1:5173")
    assert ui_destino() == "http://127.0.0.1:5173"
