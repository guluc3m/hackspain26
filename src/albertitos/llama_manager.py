"""Gestión del sidecar llama-server (escalón 4): load → process → stop.

El servidor se arranca bajo demanda la primera vez que una página necesita VLM,
se reutiliza mientras haya trabajo y se detiene tras `idle_timeout` sin uso.
No se fijan hilos ni backend: `llama` usa sus defaults (el instalador de
llama.app ya elige CUDA/ROCm/CPU según la máquina). Si el binario o el modelo
faltan, el escalón degrada (`skipped:...`) — nunca para el lote.

Estado y logs en disco del proyecto (nunca /tmp). Idempotente: si algo ya
escucha en la URL configurada, se reutiliza y no se toca al parar.
"""

import atexit
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = _PROJECT_ROOT / "models" / "llama" / "PaddleOCR-VL-1.6-GGUF.gguf"
DEFAULT_MMPROJ = _PROJECT_ROOT / "models" / "llama" / "PaddleOCR-VL-1.6-GGUF-mmproj.gguf"
DEFAULT_IDLE_TIMEOUT = 300.0  # 5 min sin trabajo ⇒ stop
_STARTUP_TIMEOUT = 180.0  # carga del GGUF + mmproj (~1 GB) en frío
_POLL = 0.5


class LlamaSidecar:
    """Arranca/reutiliza/para `llama serve` con parada por inactividad."""

    def __init__(
        self,
        base_url: str | None = None,
        model: Path | None = None,
        mmproj: Path | None = None,
        binary: str | None = None,
        idle_timeout: float | None = None,
        log_dir: Path | None = None,
    ) -> None:
        # Una sola fuente de verdad: ALBERTITOS_LLAMA_URL la lee AppConfig y
        # llega ya inyectada (base_url); aquí solo se normaliza el sufijo /v1.
        self.base_url = (base_url or DEFAULT_BASE_URL + "/v1").rstrip("/")
        if self.base_url.endswith("/v1"):
            self.base_url = self.base_url.removesuffix("/v1")
        self.model = model or Path(os.environ.get("ALBERTITOS_LLAMA_MODEL", DEFAULT_MODEL))
        self.mmproj = mmproj or Path(os.environ.get("ALBERTITOS_LLAMA_MMPROJ", DEFAULT_MMPROJ))
        self.binary = binary or os.environ.get("ALBERTITOS_LLAMA_BIN", "llama")
        self.idle_timeout = idle_timeout if idle_timeout is not None else float(
            os.environ.get("ALBERTITOS_LLAMA_IDLE_TIMEOUT", DEFAULT_IDLE_TIMEOUT)
        )
        self.log_dir = log_dir
        self._serve_mode: bool | None = None  # None = probar `serve`; False = binario clásico
        self._atexit_registered = False
        self._resolved_binary: str = self.binary
        self._lock = threading.Lock()
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_path: Path | None = None
        self._last_used = 0.0
        self._external = False  # ya estaba corriendo antes de nosotros
        self._watchdog: threading.Thread | None = None

    # -- estado ---------------------------------------------------------

    def is_up(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/health", timeout=1.0).status_code == 200
        except httpx.HTTPError:
            return False

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "up": self.is_up(),
                "managed_pid": self._proc.pid if self._proc else None,
                "external": self._external,
                "idle_s": round(time.monotonic() - self._last_used, 1) if self._last_used else None,
                "idle_timeout_s": self.idle_timeout,
                "model": str(self.model),
                "log": str(self._log_path) if self._log_path else None,
            }

    def touch(self) -> None:
        """Marcar uso reciente (cada petición del escalón 4)."""
        with self._lock:
            self._last_used = time.monotonic()

    # -- ciclo de vida ---------------------------------------------------

    def ensure_started(self, wait_s: float = _STARTUP_TIMEOUT) -> bool:
        """True si hay servidor disponible (propio o externo). No lanza."""
        if self.is_up():
            with self._lock:
                self._external = self._proc is None
                self._last_used = time.monotonic()
            return True

        with self._lock:
            # otro hilo ya está arrancando el nuestro
            if self._proc is not None and self._proc.poll() is None:
                pass
            elif not self._prerequisites_ok():
                return False
            elif self._proc is None or self._proc.poll() is not None:
                self._spawn_locked()

        return self._wait_healthy(wait_s)

    def stop(self, timeout: float = 10.0) -> None:
        with self._lock:
            proc, self._proc = self._proc, None
            self._external = False
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=timeout)

    # -- internals --------------------------------------------------------

    def _prerequisites_ok(self) -> bool:
        resolved = _resolve_binary(self.binary)
        if resolved is None:
            return False
        self._resolved_binary = resolved
        return self.model.is_file() and self.mmproj.is_file()

    def _spawn_locked(self) -> None:
        # `serve` es del CLI unificado de llama.app; el binario clásico
        # llama-server no lo entiende — se reintenta sin él (ver _wait_healthy).
        cmd = [self._resolved_binary]
        if self._serve_mode is not False:
            cmd.append("serve")
        cmd += [
            "-m",
            str(self.model),
            "--mmproj",
            str(self.mmproj),
            "--temp",
            "0",
            "--host",
            _host_port(self.base_url)[0],
            "--port",
            _host_port(self.base_url)[1],
        ]
        log_file = None
        if self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = self.log_dir / "llama-server.log"
            log_file = self._log_path.open("ab")
        # Sin --threads, sin flags de GPU: defaults de llama.cpp para esta máquina.
        popen_kwargs: dict[str, Any] = {}
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True  # Windows: ValueError si se pasa
        self._proc = subprocess.Popen(
            cmd,
            stdout=log_file or subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            **popen_kwargs,
        )
        if log_file is not None:
            log_file.close()  # el hijo ya duplicó el fd
        if not self._atexit_registered:
            atexit.register(self.stop)  # no dejar huérfanos comiendo RAM
            self._atexit_registered = True
        self._last_used = time.monotonic()
        self._external = False
        if self._watchdog is None or not self._watchdog.is_alive():
            self._watchdog = threading.Thread(target=self._watch_loop, daemon=True, name="llama-idle-watchdog")
            self._watchdog.start()

    def _wait_healthy(self, wait_s: float) -> bool:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self.is_up():
                with self._lock:
                    self._last_used = time.monotonic()
                return True
            with self._lock:
                proc = self._proc
            if proc is not None and proc.poll() is not None:
                if self._serve_mode is None:
                    # binario clásico (llama-server.exe): reintenta sin `serve`
                    self._serve_mode = False
                    with self._lock:
                        self._spawn_locked()
                    continue
                return False  # murió al arrancar (puerto ocupado, modelo inválido...)
            time.sleep(_POLL)
        return False

    def _watch_loop(self) -> None:
        while True:
            time.sleep(min(30.0, max(1.0, self.idle_timeout / 4)))
            with self._lock:
                proc = self._proc
                idle_for = time.monotonic() - self._last_used if self._last_used else 0.0
                stop_now = (
                    proc is not None
                    and proc.poll() is None
                    and not self._external
                    and idle_for >= self.idle_timeout
                )
            if stop_now:
                self.stop()




def _host_port(base_url: str) -> tuple[str, str]:
    rest = base_url.split("//", 1)[1]
    host, _, port = rest.partition(":")
    return host or "127.0.0.1", port or "8080"

def _resolve_binary(binary: str) -> str | None:
    """Ruta absoluta del binario, o None. Windows: prueba .exe en ~/.llama-app."""
    if os.sep in binary or (os.altsep and os.altsep in binary):
        return binary if Path(binary).is_file() else None
    found = shutil.which(binary)
    if found:
        return found
    for cand in (
        Path.home() / ".llama-app" / binary,  # instalador llama.app
        Path.home() / ".llama-app" / f"{binary}.exe",  # Windows
    ):
        if cand.is_file():
            return str(cand)
    return None


_manager: LlamaSidecar | None = None
_manager_lock = threading.Lock()

def get_manager(cfg: Any = None, **kwargs: Any) -> LlamaSidecar:
    """Singleton por proceso; rung 4 y CLI comparten el mismo sidecar.

    `cfg` es un AppConfig: una sola fuente de verdad para la URL (y dir de
    logs). Sin cfg, defaults — solo para debug manual.
    """
    global _manager
    with _manager_lock:
        if _manager is None:
            if cfg is not None:
                kwargs.setdefault("base_url", cfg.llama_base_url)
                kwargs.setdefault("log_dir", cfg.root)
            _manager = LlamaSidecar(**kwargs)
        return _manager


if __name__ == "__main__":  # debug manual: uv run python -m albertitos.llama_manager
    import sys

    mgr = get_manager(log_dir=Path(os.environ.get("ALBERTITOS_DATA", "data")))
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "start":
        print("up" if mgr.ensure_started() else "FAILED")
    elif action == "stop":
        mgr.stop()
        print("stopped")
    else:
        print(mgr.status())
