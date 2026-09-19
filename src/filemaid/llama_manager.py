"""Sidecar llama-server (escalón 4): se arranca al pedirlo, se para a los
5 min sin uso. Presupuesto fijo de hilos configurable; si el
binario o el modelo faltan, no lanza: ensure_started() devuelve False y el
escalón degrada (skipped:...). Si ya algo escucha en la URL, se reutiliza
y jamás se mata.
"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import httpx

from .provision import binary_path, model_paths

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
DEFAULT_IDLE_TIMEOUT = 300.0
_STARTUP_TIMEOUT = 180.0
_POLL = 0.5


class LlamaSidecar:
    def __init__(
        self,
        base_url: str | None = None,
        model: Path | None = None,
        mmproj: Path | None = None,
        binary: str = "llama",
        idle_timeout: float = DEFAULT_IDLE_TIMEOUT,
        log_dir: Path | None = None,
    ) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL + "/v1").removesuffix("/v1").rstrip("/")
        default_model, default_mmproj = model_paths()
        self.model = model or Path(os.environ.get("FILEMAID_LLAMA_MODEL", default_model))
        self.mmproj = mmproj or Path(os.environ.get("FILEMAID_LLAMA_MMPROJ", default_mmproj))
        self.binary = binary
        self.idle_timeout = idle_timeout
        self.log_dir = log_dir
        self._serve: bool | None = None  # None = probar `serve`; False = binario clásico
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_path: Path | None = None
        self._last_used = 0.0
        self._external = False
        self._lock = threading.Lock()

    def is_up(self) -> bool:
        try:
            return httpx.get(f"{self.base_url}/health", timeout=1.0).status_code == 200
        except httpx.HTTPError:
            return False

    def touch(self) -> None:
        with self._lock:
            self._last_used = time.monotonic()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "up": self.is_up(),
                "managed_pid": self._proc.pid if self._proc else None,
                "external": self._external,
                "idle_s": round(time.monotonic() - self._last_used, 1) if self._last_used else None,
                "model": str(self.model),
                "log": str(self._log_path) if self._log_path else None,
            }

    def ensure_started(self, wait_s: float = _STARTUP_TIMEOUT) -> bool:
        """True si hay servidor (propio o ajeno). Falla sin lanzar."""
        if self.is_up():
            with self._lock:
                self._external = self._proc is None
                self._last_used = time.monotonic()
            return True
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                resolved = shutil.which(self.binary) or binary_path()
                if resolved is None or not (self.model.is_file() and self.mmproj.is_file()):
                    return False
                self._spawn_locked(resolved)
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

    def _spawn_locked(self, binary: str) -> None:
        cmd = [binary]
        if self._serve is not False and Path(binary).name in {"llama", "llama.exe"}:
            cmd.append("serve")  # CLI unificado de llama.app; llama-server no lo usa
        cmd += [
            "-m", str(self.model),
            "--mmproj", str(self.mmproj),
            "--temp", "0",
            "-c", "131072",  # Contexto máximo que soporta el modelo (n_ctx_train = 131072)
            "-ctk", "q8_0",  # KV cache quantization K = q8_0
            "-ctv", "q8_0",  # KV cache quantization V = q8_0
            "-t", str(max(1, int(os.environ.get("FILEMAID_LLAMA_THREADS", "4")))),
            "-tb", str(max(1, int(os.environ.get("FILEMAID_LLAMA_THREADS", "4")))),
        ]
        host, _, port = self.base_url.split("//", 1)[1].partition(":")
        cmd += ["--host", host, "--port", port or "8080"]

        out = subprocess.DEVNULL
        if self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            self._log_path = self.log_dir / "llama-server.log"
            out = self._log_path.open("ab")
        kwargs: dict[str, Any] = {"start_new_session": True} if os.name == "posix" else {}
        self._proc = subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT, **kwargs)
        if hasattr(out, "close"):
            out.close()
        atexit.register(self.stop)
        self._last_used = time.monotonic()
        self._external = False
        threading.Thread(target=self._watch_loop, daemon=True, name="llama-idle-watchdog").start()

    def _wait_healthy(self, wait_s: float) -> bool:
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self.is_up():
                self.touch()
                return True
            with self._lock:
                proc = self._proc
            if proc is not None and proc.poll() is not None:
                if self._serve is None:  # binario clásico: reintenta sin `serve`
                    self._serve = False
                    with self._lock:
                        self._spawn_locked(str(proc.args[0]))
                    continue
                return False
            time.sleep(_POLL)
        return False

    def _watch_loop(self) -> None:
        while True:
            time.sleep(min(30.0, max(1.0, self.idle_timeout / 4)))
            with self._lock:
                idle = time.monotonic() - self._last_used if self._last_used else 0.0
                ours = self._proc is not None and self._proc.poll() is None and not self._external
            if ours and idle >= self.idle_timeout:
                self.stop()


def _loopback_base_url(url: str) -> str:
    """The local sidecar is always loopback; a remote env URL is never used."""
    from urllib.parse import urlsplit

    host = urlsplit(url).hostname or ""
    if host in {"127.0.0.1", "localhost", "::1"}:
        return url
    return DEFAULT_BASE_URL + "/v1"


_manager: LlamaSidecar | None = None
_manager_lock = threading.Lock()


def get_manager(cfg: Any = None, **kwargs: Any) -> LlamaSidecar:
    """Singleton por proceso. `cfg` (AppConfig) = una sola fuente de la URL."""
    global _manager
    with _manager_lock:
        if _manager is None:
            if cfg is not None:
                kwargs.setdefault("base_url", _loopback_base_url(cfg.llama_base_url))
                kwargs.setdefault("log_dir", cfg.root)
            _manager = LlamaSidecar(**kwargs)
        return _manager


if __name__ == "__main__":  # debug: uv run python -m filemaid.llama_manager [start|stop]
    import sys

    mgr = get_manager(log_dir=Path(os.environ.get("FILEMAID_DATA", "data")))
    action = sys.argv[1] if len(sys.argv) > 1 else "status"
    if action == "start":
        print("up" if mgr.ensure_started() else "FAILED")
    elif action == "stop":
        mgr.stop()
        print("stopped")
    else:
        print(mgr.status())
