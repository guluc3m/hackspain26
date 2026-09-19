"""App de escritorio para Alberto (T35) — pywebview sobre la UI real.

ADR-06 (resumen en el informe): Electron descartado con argumento — runtime
de ~200 MB, toolchain Node extra, y un .exe/.dmg firmado exige una máquina
por OS (no compilable desde Linux). Elegido pywebview: ventana NATIVA del OS
(WebKit en Mac, WebView2/Edge en Windows, GTK en Linux) con nuestro stack
Python, sin Node ni navegador.

Uso:   uv run python -m albertitos.desktop
Fallback: si el webview no está disponible (CI, Linux sin GTK webkit), se
avisa en español y se abre el navegador apuntando a la misma UI — mismo
resultado con un paso menos. Cerrar la ventana apaga el servidor limpio.
"""

from __future__ import annotations

import os
import threading
import time
import webbrowser
from pathlib import Path

from albertitos.ui.app import create_app

TITULO = "Albertitos — Facturas y decisiones"


def _store_dir() -> Path:
    """El mismo contrato que la UI: ALBERTITOS_STORE (lote 1 por defecto)."""
    return Path(os.environ.get("ALBERTITOS_STORE", ".sdd/ledger"))


def arrancar_servidor(store_dir: Path | None = None, port: int = 0):
    """Arranca uvicorn en un hilo daemon (puerto efímero por defecto).

    Devuelve (server, url). El server queda sirviendo hasta `apagar()`.
    """
    import uvicorn

    aplicacion = create_app(store_dir=store_dir if store_dir is not None
                            else _store_dir())
    config = uvicorn.Config(
        aplicacion, host="127.0.0.1", port=port, log_level="warning",
    )
    server = uvicorn.Server(config)
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    # puerto real cuando el socket arranca (port=0 ⇒ efímero)
    for _ in range(200):
        if server.started:
            break
        time.sleep(0.05)
    puerto = config.port
    if puerto == 0 and getattr(server, "servers", None):
        sockets = server.servers[0].sockets
        if sockets:
            puerto = sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{puerto}"


def apagar(server) -> None:
    """Apagado limpio: el hilo daemon muere con el proceso; señalamos
    should_exit para que uvicorn cierre el socket sin traceback."""
    server.should_exit = True
    for _ in range(100):  # hasta ~5 s: cortesía de cierre
        if not server.started:
            break
        time.sleep(0.05)


def _esperar_listo(url: str, timeout_s: float = 20.0) -> bool:
    """Espera a que la UI responda (una sola prueba, sin retry infinito)."""
    import urllib.request

    fin = time.monotonic() + timeout_s
    while time.monotonic() < fin:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            time.sleep(0.2)
    return False


def abrir_ventana(url: str) -> bool:
    """Abre la ventana nativa con pywebview. False si el paquete/init falla
    (⇒ el llamador degrada a navegador con aviso en español)."""
    try:
        import webview  # opcional: pywebview[desktop]
    except ImportError:
        return False
    try:
        webview.create_window(TITULO, url, width=1400, height=900)
        webview.start()  # bloquea hasta que Alberto cierra la ventana
    except Exception as e:  # noqa: BLE001 — GTK/WebKit/WebView2: cualquier fallo de init degrada
        print(f"Aviso: la ventana nativa no se pudo abrir ({e}).")
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    store = _store_dir()
    server, url = arrancar_servidor(store)
    listo = _esperar_listo(url)
    if not listo:
        print(f"La UI tarda en responder en {url} — se abre igualmente.")

    print(f"Albertitos: {url}")
    if abrir_ventana(url):
        pass  # Alberto cerró la ventana: fin ordenado
    else:
        print(
            "Ventana nativa no disponible (falta pywebview o el webkit del "
            "escritorio). Abriendo el navegador con la misma interfaz."
        )
        webbrowser.open(url)
        print("Cierra con Ctrl+C cuando termines.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass

    apagar(server)
    print("Servidor detenido. Hasta luego, Alberto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())