"""Ventana nativa (pywebview) con la misma UI Vue.

La app (Python) aloja el front construido (frontend/dist) y expone a la UI un
puente (window.pywebview.api). Ese puente existe SOLO en la ventana nativa: el
navegador no lo tiene, así que el selector nativo de carpeta y la vigilancia no
están expuestos por ninguna ruta HTTP.

El vigilante entrega los PDF estables de la carpeta elegida a la misma ruta de
ingestión que usa el worker; la notificación de disputa se dispara solo con el
resultado final ESCALAR.

Con `--headless` no se abre ventana: se sirve la misma UI y API en loopback,
para máquinas sin display.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
from pathlib import Path
from typing import Any, Self

from filemaid.config import AppConfig
from filemaid.desktop.notify import Notificador
from filemaid.desktop.watcher import Watcher


class Api:
    """Superficie expuesta a la UI: window.pywebview.api (solo ventana nativa).

    `ping` es infraestructura del puente. `elegir_carpeta` y `vigilancia_*` son
    la vigilancia de carpeta; `arrancar_vigilancia`/`detener_vigilancia` son sus
    ganchos de ciclo de vida. No existe ninguna ruta HTTP equivalente.
    """

    def __init__(self, cfg: AppConfig | None = None) -> None:
        self.cfg = cfg or AppConfig.load()
        self.notificador = Notificador()
        self.watcher = Watcher(self.cfg, self.notificador)

    def ping(self) -> str:
        """Comprueba que el puente JS -> Python está vivo."""
        return "pong"

    def elegir_carpeta(self) -> dict:
        """Selector nativo de carpeta; devuelve la ruta elegida o None."""
        try:
            import webview

            seleccion = webview.windows[0].create_file_dialog(webview.FileDialog.FOLDER)
        except Exception as exc:
            return {"path": None, "error": f"no se pudo abrir el selector de carpeta: {exc}"}
        if not seleccion:
            return {"path": None, "error": ""}
        return {"path": str(seleccion[0]), "error": ""}

    def vigilancia_estado(self) -> dict:
        """Estado del vigilante: selección, actividad, errores y notificaciones."""
        return self.watcher.estado()

    def vigilancia_configurar(self, folder: str, enabled: bool) -> dict:
        """Valida y persiste la carpeta vigilada; arranca o pausa el sondeo."""
        return self.watcher.configurar(folder, enabled)

    def vigilancia_escanear(self) -> dict:
        """Un sondeo inmediato de la carpeta elegida (aplica el dedup)."""
        return self.watcher.escanear()

    def arrancar_vigilancia(self) -> None:
        """Prepara el notificador y arranca el vigilante si estaba activo."""
        self.notificador.preparar()
        self.notificador.probar()
        if self.watcher.estado()["enabled"]:
            self.watcher.start()

    def detener_vigilancia(self) -> None:
        """Para el vigilante; idempotente y acotado (cierre de ventana y atexit)."""
        self.watcher.stop()


def _dist_index() -> Path:
    """Índice del build de la UI (frontend/dist), relativo a este módulo."""
    return Path(__file__).resolve().parents[3] / "frontend" / "dist" / "index.html"


def ui_destino(runtime: _Runtime) -> str:
    """Qué carga la ventana: URL de dev (FILEMAID_UI_URL) o el build dist."""
    url = os.environ.get("FILEMAID_UI_URL", "")
    if url:
        return url
    if _dist_index().exists():
        return runtime.api.start()
    raise SystemExit(
        "UI no construida: python start.py client (o FILEMAID_UI_URL=http://127.0.0.1:5173 con dev)"
    )


class _ApiServer:
    """FastAPI local en un puerto loopback elegido por el SO.

    Es un recurso propio del proceso: `stop()` lo para de forma acotada y deja
    que el `lifespan` de la app cierre sus servicios (p. ej. la ingestión). No
    se registra solo en `atexit`: el cierre de la ventana lo para explícitamente
    para que la salida sea determinista.
    """

    JOIN_S = 5.0

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sock: socket.socket | None = None
        self._server: Any = None
        self._thread: threading.Thread | None = None
        self.url = ""

    def start(self) -> str:
        import time

        import uvicorn

        from filemaid.api.app import create_app

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(create_app(), log_level="warning"))
        thread = threading.Thread(
            target=server.run, kwargs={"sockets": [sock]}, daemon=True, name="filemaid-api"
        )
        thread.start()
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        if not server.started:
            sock.close()
            raise RuntimeError("No se pudo arrancar FastAPI local")
        with self._lock:
            self._sock, self._server, self._thread = sock, server, thread
            self.url = f"http://127.0.0.1:{port}"
        return self.url

    def stop(self) -> bool:
        """Para el servidor y espera su cierre; False si no terminó a tiempo."""
        with self._lock:
            server, thread, sock = self._server, self._thread, self._sock
            self._server = self._thread = self._sock = None
        if server is None:
            return True
        server.should_exit = True
        stopped = True
        if thread is not None:
            thread.join(timeout=self.JOIN_S)
            stopped = not thread.is_alive()
        if sock is not None:
            sock.close()
        return stopped


class _Runtime:
    """Recursos propios de este proceso, parados en orden al cerrar la ventana.

    Solo se para lo que este proceso arrancó. Un llama-server ya en marcha
    (ajeno, o de otra instancia nativa) se reutiliza y nunca se mata, y las
    demás instancias no se tocan: cada una cierra únicamente lo suyo.
    """

    def __init__(self, cfg: AppConfig | None = None) -> None:
        self.cfg = cfg
        self.api = _ApiServer()
        self._closed = False

    def close(self) -> dict[str, bool]:
        """Para API, sidecar propio y aprovisionador; informa de cada cierre.

        El sidecar se para antes que el aprovisionador: su espera de salud es lo
        único que puede tener al aprovisionador bloqueado, así que cerrarlo
        primero hace que ese hilo termine en el siguiente sondeo en vez de
        agotar su plazo.
        """
        if self._closed:
            return {}
        self._closed = True
        results: dict[str, bool] = {}
        for name, stop in (
            ("api", self.api.stop),
            ("llama", self._stop_llama),
            ("provision", self._stop_provision),
        ):
            try:
                results[name] = bool(stop())
            except Exception as exc:
                results[name] = False
                print(f"[filemaid] el cierre de {name} falló: {exc}", file=sys.stderr)
        return results

    def _stop_provision(self) -> bool:
        from filemaid.provision import get_provisioner

        return get_provisioner(self.cfg).stop()

    def _stop_llama(self) -> bool:
        from filemaid.llama_manager import get_manager

        return get_manager(self.cfg).shutdown()


def _gui_backend() -> str | None:
    """Backend explícito si QT está disponible en Linux o Windows.

    Con gui='qt' pywebview no sondea GTK (Linux) ni cae a MSHTML si falta el
    runtime WebView2 (Windows): el bundle Vue usa módulos ES y MSHTML no los
    soporta. En otras plataformas se deja la selección automática (backends
    nativos).
    """
    if sys.platform not in {"linux", "win32"}:
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
        self._activo = False
        self._lock = threading.Lock()
        self._captura = bytearray()

    def __enter__(self) -> Self:
        try:
            self._viejo = os.dup(2)
        except OSError:
            # Sin fd 2 válido (p. ej. pythonw en Windows): no hay nada que capturar.
            self._activo = False
            return self
        self._activo = True
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
        if not self._activo:
            return
        os.dup2(self._viejo, 2)
        os.close(self._w)
        self._cerrado.set()
        self._drenador.join(timeout=1.0)

    def __exit__(self, *exc: object) -> None:
        self.restaurar()
        if not self._activo:
            return
        os.close(self._r)
        os.close(self._viejo)

    def texto(self) -> str:
        with self._lock:
            return self._captura.decode(errors="replace")


def _serve_headless(port: int) -> int:
    """Sirve la UI y la API en loopback sin abrir ventana (sin display)."""
    import uvicorn

    from filemaid.api.app import create_app

    uvicorn.run(create_app(), host="127.0.0.1", port=port)
    return 0


def _arrancar_vigilancia(api: Api) -> None:
    """Arranca el vigilante de carpeta si el usuario lo dejó activo."""
    try:
        api.arrancar_vigilancia()
    except Exception as exc:
        print(f"[filemaid] no se pudo arrancar el vigilante: {exc}", file=sys.stderr)


def _detener_vigilancia(api: Api) -> None:
    """Para el vigilante; idempotente y acotado (cierre de ventana y atexit)."""
    try:
        api.detener_vigilancia()
    except Exception as exc:
        print(f"[filemaid] el vigilante no se detuvo limpiamente: {exc}", file=sys.stderr)


def _cerrar(runtime: _Runtime) -> None:
    """Cierra los recursos propios y garantiza que el proceso termina.

    Un trabajador atascado (p. ej. una llamada al puente PouchDB) no debe
    mantener viva la app tras cerrar la ventana: si algo no paró dentro de su
    plazo, se sale en duro en vez de dejar que el intérprete espere a un hilo
    que no va a terminar.
    """
    pendientes = [name for name, ok in runtime.close().items() if not ok]
    if not pendientes:
        return
    print(
        f"[filemaid] cierre forzado: {', '.join(pendientes)} no terminó a tiempo",
        file=sys.stderr,
    )
    sys.stderr.flush()
    os._exit(0)


def main(argv: list[str] | None = None) -> int:
    import argparse
    import atexit

    parser = argparse.ArgumentParser(
        prog="filemaid-desktop", description="UI de filemaid: ventana nativa o servicio headless"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="sirve la UI y la API en loopback sin abrir ventana (máquinas sin display)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FILEMAID_PORT", "8000")),
        help="puerto loopback en modo headless (por defecto FILEMAID_PORT o 8000)",
    )
    args = parser.parse_args(argv)

    if args.headless:
        return _serve_headless(args.port)

    try:
        import webview
    except ImportError:
        raise SystemExit("falta pywebview: uv sync --extra desktop")

    runtime = _Runtime(AppConfig.load())
    api = Api(runtime.cfg)
    # Red de seguridad para salidas que no pasan por el cierre de la ventana
    # (excepción, señal): el camino normal es el `finally` de abajo.
    atexit.register(_cerrar, runtime)
    atexit.register(_detener_vigilancia, api)

    ventana = webview.create_window(
        "filemaid — decisión de facturas",
        ui_destino(runtime),
        js_api=api,
        width=1280,
        height=860,
    )
    ventana.events.closed += lambda *_: _detener_vigilancia(api)

    def _al_cargar(*_: object) -> None:
        # El vigilante se arranca con la página ya cargada: su notificador usa
        # Qt, y la aplicación Qt solo existe dentro de `webview.start()`.
        arranque.restaurar()
        _arrancar_vigilancia(api)

    with _StderrArranque() as arranque:
        ventana.events.loaded += _al_cargar
        try:
            webview.start(gui=_gui_backend())
        except Exception as exc:
            # sin GTK/QT con extensiones Python en el sistema (p.ej. entorno
            # sin raíz), la ventana nativa no puede abrirse; el ruido capturado
            # puede incluir el diagnóstico de la sonda que falló
            raise SystemExit(f"la ventana nativa no pudo arrancar: {exc}\n{arranque.texto()}")
        finally:
            # Cerrar la ventana termina el proceso: se para el vigilante y todo
            # lo que este proceso arrancó (API, aprovisionador, sidecar propio).
            # Minimizar no pasa por aquí: la ventana sigue viva y el vigilante
            # sigue trabajando en segundo plano.
            _detener_vigilancia(api)
            _cerrar(runtime)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
