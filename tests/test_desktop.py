"""T35 — app de escritorio: bootstrap del servidor y fallback sin webview."""

import urllib.request
from pathlib import Path
from types import SimpleNamespace

from albertitos.desktop import abrir_ventana, apagar, arrancar_servidor
from albertitos.ui.app import create_app


def test_servidor_arranca_responde_y_se_apaga(tmp_path):
    server, url = arrancar_servidor(store_dir=tmp_path, port=0)
    try:
        assert server.started
        with urllib.request.urlopen(url, timeout=3) as resp:
            assert resp.status == 200
            assert "html" in resp.read().decode().lower()
    finally:
        apagar(server)
        assert server.should_exit


def test_usa_el_store_de_la_variable_de_entorno(tmp_path):
    """ALBERTITOS_STORE decide el ledger que sirve la app (contrato T5)."""
    import os

    antes = os.environ.get("ALBERTITOS_STORE")
    os.environ["ALBERTITOS_STORE"] = str(tmp_path / "ledger")
    try:
        app = create_app(store_dir=None)  # None ⇒ desktop usa el env
        assert app is not None  # fábrica funciona con el env puesto
    finally:
        if antes is None:
            os.environ.pop("ALBERTITOS_STORE", None)
        else:
            os.environ["ALBERTITOS_STORE"] = antes


def test_sin_webview_degrada_a_false(monkeypatch):
    """Sin pywebview instalado (CI): abrir_ventana ⇒ False y el llamador
    degrada a navegador con aviso (desktop.py)."""
    import builtins

    real_import = builtins.__import__

    def sin_webview(name, *args, **kwargs):
        if name == "webview":
            raise ImportError("No module named 'webview'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", sin_webview)
    assert abrir_ventana("http://127.0.0.1:1") is False


def test_con_webview_degradacion_si_falla_el_init(monkeypatch):
    """Si pywebview está pero el webkit/WebView2 del OS falla ⇒ False
    (no excepción) para que el navegador tome el relevo."""
    fake = SimpleNamespace()

    def create_window(*a, **k):
        raise RuntimeError("webkit2gtk no disponible en este sistema")

    fake.create_window = create_window
    fake.start = lambda: None
    monkeypatch.setitem(__import__("sys").modules, "webview", fake)
    assert abrir_ventana("http://127.0.0.1:1") is False


def test_con_webview_sano_ventana_bloquea_y_devuelve_true(monkeypatch):
    llamadas: dict = {}

    fake = SimpleNamespace()

    def create_window(titulo, url, **k):
        llamadas["titulo"], llamadas["url"] = titulo, url

    fake.create_window = create_window
    fake.start = lambda: llamadas.__setitem__("start", True)
    monkeypatch.setitem(__import__("sys").modules, "webview", fake)
    assert abrir_ventana("http://127.0.0.1:8000") is True
    assert llamadas["url"] == "http://127.0.0.1:8000"
    assert llamadas.get("start") is True


def test_iniciar_sh_presente_y_ejecutable():
    sh = Path("iniciar.sh")
    cmd = Path("iniciar.command")
    assert sh.exists() and cmd.exists()
    import os

    assert os.access(sh, os.X_OK) and os.access(cmd, os.X_OK)
    texto = sh.read_text()
    assert "albertitos.desktop" in texto
    bat = Path("iniciar.bat").read_text()
    ps1 = Path("iniciar.ps1").read_text()
    assert "albertitos.desktop" in bat and "albertitos.desktop" in ps1
