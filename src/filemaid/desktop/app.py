"""Ventana nativa (pywebview) con la misma UI Vue.

La app (Python) aloja el front construido (frontend/dist) y expone a la UI un
puente (window.pywebview.api) capaz de llamar a los dos motores de la
arquitectura: engines.extraction y engines.decision.

La conexión real utiliza el mismo FastAPI local que el navegador. Los motores
del puente histórico no participan en la persistencia de ingestión.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Self

from filemaid.engines import DecisionEngine, ExtractionEngine


class Api:
    """Superficie expuesta a la UI: window.pywebview.api.

    ping es infraestructura del puente; extraer y decidir son las llamadas a
    los motores, aún sin definir.
    """

    def __init__(self) -> None:
        self.extraction = ExtractionEngine()
        self.decision = DecisionEngine()

    def ping(self) -> str:
        """Comprueba que el puente JS -> Python está vivo."""
        return "pong"

    def extraer(self, file_id: str) -> object:
        """PDF -> campos: llamada al motor de extracción (sin definir).

        La resolución de la ruta del PDF a partir del file_id se definirá
        junto con la llamada.
        """
        return self.extraction.extraer(file_id)

    def decidir(self, invoice_id: str) -> object:
        """Campos -> decisión: llamada al motor de decisión (sin definir).

        La carga de los campos almacenados para la factura se definirá junto
        con la llamada; los argumentos son provisionales.
        """
        # llamada sin definir: el motor lanza NotImplementedError
        return self.decision.decidir([], invoice_id, invoice_id)


def _dist_index() -> Path:
    """Índice del build de la UI (frontend/dist), relativo a este módulo."""
    return Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"


def ui_destino() -> str:
    """Qué carga la ventana: URL de dev (ALBERTITOS_UI_URL) o el build dist."""
    url = os.environ.get("ALBERTITOS_UI_URL", "")
    if url:
        return url
    dist = _dist_index()
    if dist.exists():
        return _start_api()
    raise SystemExit(
        "UI no construida: uv run -- npm --prefix frontend run build "
        "(o ALBERTITOS_UI_URL=http://127.0.0.1:5173 con dev)"
    )


def _start_api() -> str:
    """Serve the built UI and API on an OS-selected loopback port."""
    import atexit
    import socket
    import time

    import uvicorn

    from filemaid.api.app import create_app

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.02)
    if not server.started:
        sock.close()
        raise RuntimeError("No se pudo arrancar FastAPI local")

    def stop():
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()

    atexit.register(stop)
    return f"http://127.0.0.1:{port}"


def _gui_backend() -> str | None:
    """Backend explícito si QT está disponible en Linux.

    Con gui='qt' pywebview no sondea GTK: evita el ruido
    '[pywebview] GTK cannot be loaded' en cada arranque. En otras
    plataformas se deja la selección automática (backends nativos).
    """
    if sys.platform != "linux":
        return None
    try:
        import qtpy  # noqa: F401
    except ImportError:
        return None
    return "qt"


class _StderrArranque:
    """stderr bajo llave durante el arranque de la ventana.

    Algunas sondas del sistema (Vulkan, VA-API) escriben directamente en
    fd 2 al inicializar la ventana y no se pueden silenciar por
    configuración. Durante el arranque se capturan; cuando la página carga
    (o vence un plazo de seguridad) stderr vuelve a la normalidad. Si el
    arranque falla, lo capturado acompaña al error como diagnóstico.
    """

    PLAZO_S = 15.0
    TOPE_BYTES = 16384

    def __init__(self) -> None:
        self._restaurado = False
        self._lock = threading.Lock()
        self._captura = bytearray()

    def __enter__(self) -> Self:
        self._viejo = os.dup(2)
        self._r, self._w = os.pipe()
        os.dup2(self._w, 2)
        self._cerrado = threading.Event()
        self._drenador = threading.Thread(target=self._drenar, daemon=True)
        self._drenador.start()
        # plazo de seguridad: si la página nunca carga, stderr vuelve igual
        vigilante = threading.Timer(self.PLAZO_S, self.restaurar)
        vigilante.daemon = True
        vigilante.start()
        return self

    def _drenar(self) -> None:
        while not self._cerrado.is_set():
            try:
                trozo = os.read(self._r, 4096)
            except OSError:
                break
            if not trozo:
                break
            with self._lock:
                if len(self._captura) < self.TOPE_BYTES:
                    self._captura.extend(trozo)

    def restaurar(self) -> None:
        with self._lock:
            if self._restaurado:
                return
            self._restaurado = True
        os.dup2(self._viejo, 2)
        os.close(self._w)
        self._cerrado.set()
        self._drenador.join(timeout=1.0)

    def __exit__(self, *exc: object) -> None:
        self.restaurar()
        os.close(self._r)
        os.close(self._viejo)

    def texto(self) -> str:
        with self._lock:
            return self._captura.decode(errors="replace")


def main() -> int:
    try:
        import webview
    except ImportError:
        raise SystemExit("falta pywebview: uv sync --extra desktop")

    ventana = webview.create_window(
        "albertitos — decisión de facturas",
        ui_destino(),
        js_api=Api(),
        width=1280,
        height=860,
    )
    with _StderrArranque() as arranque:
        ventana.events.loaded += lambda *_: arranque.restaurar()
        try:
            webview.start(gui=_gui_backend())
        except Exception as exc:
            # sin GTK/QT con extensiones Python en el sistema (p.ej. entorno
            # sin raíz), la ventana nativa no puede abrirse; el ruido capturado
            # puede incluir el diagnóstico de la sonda que falló
            raise SystemExit(f"la ventana nativa no pudo arrancar: {exc}\n{arranque.texto()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
