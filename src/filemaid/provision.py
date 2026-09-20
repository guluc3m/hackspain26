"""VLM provisioning: PaddleOCR-VL full-Q8 (D-002) + llama.cpp sidecar readiness.

Acquisition reuses ``scripts/setup_llama.{sh,ps1}`` (official llama.app
installer + HuggingFace weights with sha256 verification). This module never
claims the model is ready unless the sidecar process is running and healthy:
files on disk are ``downloaded``, a healthy ``/health`` is ``ready``.

The install manifest is a device-local PouchDB doc (``_local/provision-manifest``),
never a loose ``.json`` file; on restart readiness is re-derived from the actual
files and process, not from the manifest.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .processes import terminate_tree

# D-002: Mungert full-Q8 (text q8_0 + vision mmproj q8_0). The official
# PaddlePaddle repo ships bf16/f16, not Q8; Q8 is the safe quality floor.
MODEL_REPO = "Mungert/PaddleOCR-VL-1.6-GGUF"
MODEL_FILES: tuple[tuple[str, int, str], ...] = (
    (
        "PaddleOCR-VL-1.6-q8_0.gguf",
        498316064,
        "58ff75f8ca2ad8bc4308324d0df570ef77832479b2a80091134fc33e11955a3a",
    ),
    (
        "PaddleOCR-VL-1.6-q8_0.mmproj",
        597566368,
        "036d06ea82e9133696c2f93bd9dd2e1e5009520811e5fb3092aab2d0e5696375",
    ),
)
GGUF_NAME, MMPROJ_NAME = MODEL_FILES[0][0], MODEL_FILES[1][0]
MANIFEST_ID = "provision-manifest"
_SETUP_TIMEOUT = 3600.0


def repo_root() -> Path:
    """Repo root: nearest ancestor holding scripts/setup_llama.sh."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "scripts" / "setup_llama.sh").is_file():
            return parent
    return here.parents[3]


def models_dir() -> Path:
    return Path(os.environ.get("FILEMAID_MODELS", str(repo_root() / "models" / "llama")))


def model_paths() -> tuple[Path, Path]:
    base = models_dir()
    return base / GGUF_NAME, base / MMPROJ_NAME


def binary_path() -> str | None:
    """Resolve the llama.cpp binary: unified `llama` or classic `llama-server`."""
    for name in ("llama", "llama-server"):
        found = shutil.which(name)
        if found:
            return found
    for name in ("llama", "llama.exe", "llama-server", "llama-server.exe"):
        cand = Path.home() / ".llama-app" / name
        if cand.is_file():
            return str(cand)
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files_ready() -> bool:
    """Both weights present with the expected size (fast; no hashing)."""
    for name, size, _sha in MODEL_FILES:
        path = models_dir() / name
        if not path.is_file() or path.stat().st_size != size:
            return False
    return True


def missing_files() -> list[str]:
    return [
        name
        for name, size, _sha in MODEL_FILES
        if not (models_dir() / name).is_file() or (models_dir() / name).stat().st_size != size
    ]


def download_progress() -> dict[str, Any]:
    """Observed download progress from bytes on disk, not invented values.

    The setup helpers download to ``<name>.part`` and rename on success, so the
    partial size is exactly what has landed. ``progress`` (0..1) is ``None``
    while nothing partial is observable — e.g. the llama.cpp binary phase — so
    the UI shows an indeterminate state instead of a fake 0 %.
    """
    total = sum(size for _name, size, _sha in MODEL_FILES)
    done = 0
    current: str | None = None
    for name, size, _sha in MODEL_FILES:
        final = models_dir() / name
        part = models_dir() / f"{name}.part"
        if part.is_file():
            # A .part beats the final file: the helper re-downloads to .part
            # when weights are corrupt, so the final copy there is stale.
            done += min(part.stat().st_size, size)
            current = name
        elif final.is_file() and final.stat().st_size == size:
            done += size
    progress: float | None = round(done / total, 4) if done else None
    if total and done >= total:
        progress = 1.0
    return {"progress": progress, "bytes_done": done, "bytes_total": total, "file": current}


def verify_weights() -> list[str]:
    """Full sha256 verification of the weights; returns the names that mismatch."""
    bad: list[str] = []
    for name, size, sha in MODEL_FILES:
        path = models_dir() / name
        if not path.is_file() or path.stat().st_size != size or _sha256_file(path) != sha:
            bad.append(name)
    return bad


def setup_script() -> Path:
    root = repo_root()
    return root / "scripts" / ("setup_llama.ps1" if os.name == "nt" else "setup_llama.sh")


def run_setup(log_path: Path | None = None, *, track: Any = None) -> None:
    """Run the platform setup helper (downloads binary + weights). Raises on failure.

    `track` recibe el proceso hijo mientras vive (y `None` al terminar), para que
    quien aprovisiona pueda cortarlo al cerrar la app en vez de dejar una
    descarga huérfana.
    """
    script = setup_script()
    if not script.is_file():
        raise RuntimeError(f"setup helper not found: {script}")
    env = {**os.environ, "FILEMAID_MODELS": str(models_dir()), "LLAMA_MODEL_REPO": MODEL_REPO}
    if os.name == "nt":
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    else:
        cmd = ["sh", str(script)]
    out: Any = subprocess.DEVNULL
    handle = None
    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = log_path.open("ab")
        out = handle
    # Sesión propia en POSIX: el ayudante lanza descargas hijas y solo así se
    # puede terminar el árbol completo al cerrar.
    kwargs: dict[str, Any] = {"start_new_session": True} if os.name == "posix" else {}
    try:
        proc = subprocess.Popen(cmd, env=env, stdout=out, stderr=subprocess.STDOUT, **kwargs)
        if track is not None:
            track(proc)
        try:
            code = proc.wait(timeout=_SETUP_TIMEOUT)
        except subprocess.TimeoutExpired:
            terminate_tree(proc)
            raise RuntimeError(f"setup helper timed out after {_SETUP_TIMEOUT:.0f}s") from None
    finally:
        if track is not None:
            track(None)
        if handle is not None:
            handle.close()
    if code != 0:
        raise RuntimeError(f"setup helper failed with exit code {code}")


class VlmProvisioner:
    """Owns local VLM acquisition + sidecar start; exposes truthful state."""

    def __init__(self, cfg: Any = None, log_dir: Path | None = None) -> None:
        self.cfg = cfg
        self.log_dir = log_dir or (cfg.root if cfg is not None else None)
        self._lock = threading.RLock()
        self._state = "idle"
        self._detail = ""
        self._error = ""
        self._thread: threading.Thread | None = None
        self._setup_proc: subprocess.Popen[bytes] | None = None
        self._closed = threading.Event()

    # -- public -----------------------------------------------------------

    def status(self) -> dict[str, Any]:
        with self._lock:
            state, detail, error = self._state, self._detail, self._error
            thread = self._thread
        in_flight = thread is not None and thread.is_alive()
        downloaded = files_ready()
        running = self._sidecar_up()
        if state in {"downloading", "starting"}:
            if in_flight:
                ready = False
            elif downloaded and running:
                # La verdad observada manda: ya hay sidecar sano sirviendo el modelo.
                state, detail, error, ready = "ready", "sidecar healthy", "", True
            else:
                # Un intento que ya no corre no puede leerse como "preparando".
                state, detail, error, ready = "idle", "not running", "", False
        elif state == "error":
            ready = False
        else:
            ready = downloaded and running
            state = "ready" if ready else "idle"
        gguf, mmproj = model_paths()
        return {
            "state": state,
            "in_flight": in_flight,
            "downloaded": downloaded,
            "running": running,
            "ready": ready,
            "detail": detail,
            "error": error,
            **download_progress(),
            "model": str(gguf),
            "mmproj": str(mmproj),
            "binary": binary_path(),
        }

    def ensure(self, wait: bool = False) -> dict[str, Any]:
        """Idempotently install (if needed) + start + health-check the sidecar."""
        thread: threading.Thread | None = None
        with self._lock:
            if self._closed.is_set():
                return self.status()
            if self._thread is not None and self._thread.is_alive():
                thread = self._thread
            elif files_ready() and self._sidecar_up() and self._manifest_verified():
                # Only shortcut when this data root already recorded a verified
                # install; a new cfg must verify + persist the manifest first.
                self._state, self._detail, self._error = "ready", "sidecar healthy", ""
            else:
                self._thread = threading.Thread(
                    target=self._run, name="vlm-provision", daemon=True
                )
                thread = self._thread
                thread.start()
        if thread is not None and wait:
            thread.join()
        return self.status()

    def stop(self, timeout: float = 5.0) -> bool:
        """Corta el aprovisionamiento propio: descarga incluida, sin reanudar.

        Idempotente y acotado. El hilo es daemon, así que un cierre lento nunca
        bloquea la salida del proceso; el valor devuelto solo informa de si
        terminó dentro del plazo.
        """
        self._closed.set()
        with self._lock:
            proc, self._setup_proc = self._setup_proc, None
            thread = self._thread
            if self._state in {"downloading", "starting"}:
                # Un cierre aborta la descarga/arranque: el estado no puede quedar
                # clavado en "preparando" cuando ya no hay nada en marcha.
                self._state, self._detail, self._error = "idle", "not running", ""
        if proc is not None:
            terminate_tree(proc, timeout)
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        return not (thread is not None and thread.is_alive())

    # -- internals --------------------------------------------------------

    def _set(self, state: str, detail: str = "", error: str = "") -> None:
        with self._lock:
            self._state, self._detail, self._error = state, detail, error

    def _run(self) -> None:
        try:
            log_path = (self.log_dir / "vlm-provision.log") if self.log_dir else None
            if not files_ready() or binary_path() is None:
                self._set("downloading", "downloading PaddleOCR-VL Q8 weights + llama.cpp")
                run_setup(log_path, track=self._track_setup)
            if self._closed.is_set():
                return
            if not files_ready():
                self._set("error", "", f"weights incomplete: {', '.join(missing_files())}")
                return
            if binary_path() is None:
                self._set("error", "", "llama binary not found after setup")
                return
            # Acquisition must sha256-verify existing same-size weights, not only
            # missing downloads: a corrupt file must never be marked verified.
            mismatched = verify_weights()
            if mismatched:
                self._set("downloading", f"re-downloading corrupt weights: {', '.join(mismatched)}")
                run_setup(log_path, track=self._track_setup)
                if self._closed.is_set():
                    return
                mismatched = verify_weights()
                if mismatched:
                    self._set("error", "", f"sha256 mismatch: {', '.join(mismatched)}")
                    return
            self._set("starting", "starting llama-server")
            from filemaid.llama_manager import get_manager

            mgr = get_manager(self.cfg)
            if not mgr.ensure_started():
                if self._closed.is_set():
                    return
                self._set("error", "", "llama-server did not become healthy")
                return
            if not self._serves_expected_model(mgr.base_url):
                self._set(
                    "error", "", "endpoint is not serving the expected PaddleOCR-VL model"
                )
                return
            self._write_manifest()
            self._set("ready", "sidecar healthy")
        except Exception as exc:
            # Un cierre en curso no es un fallo del aprovisionamiento.
            if self._closed.is_set():
                return
            self._set("error", "", f"{type(exc).__name__}: {exc}")

    def _track_setup(self, proc: subprocess.Popen[bytes] | None) -> None:
        with self._lock:
            self._setup_proc = proc

    def _sidecar_up(self) -> bool:
        try:
            from filemaid.llama_manager import get_manager

            mgr = get_manager(self.cfg)
            if not mgr.is_up():
                return False
            # A healthy /health is not enough: an arbitrary process may occupy
            # the port. Verify the endpoint actually serves our model.
            return self._serves_expected_model(mgr.base_url)
        except Exception:
            return False

    @staticmethod
    def _serves_expected_model(base_url: str) -> bool:
        import httpx

        try:
            response = httpx.get(f"{base_url}/v1/models", timeout=2.0)
            if response.status_code != 200:
                return False
            models = response.json().get("data", [])
            ids = [str(m.get("id", "")) for m in models if isinstance(m, dict)]
        except Exception:
            return False
        stem = GGUF_NAME.removesuffix(".gguf")
        return any(stem in model_id for model_id in ids)

    def _manifest_verified(self) -> bool:
        """True only if this data root recorded a verified install of these files."""
        if self.cfg is None:
            return False
        try:
            from filemaid.store.pouch import PouchStore

            saved = PouchStore(self.cfg.root).local_get(MANIFEST_ID)
        except Exception:
            return False
        if not isinstance(saved, dict):
            return False
        recorded = {
            f.get("name"): f.get("sha256")
            for f in saved.get("files", [])
            if isinstance(f, dict)
        }
        return all(recorded.get(name) == sha for name, _size, sha in MODEL_FILES)

    def _write_manifest(self) -> None:
        """Persist the verified install manifest in PouchDB; failure is visible."""
        if self.cfg is None:
            return
        from filemaid.store.pouch import PouchStore

        PouchStore(self.cfg.root).local_put(
            MANIFEST_ID,
            {
                "model_repo": MODEL_REPO,
                "files": [
                    {"name": name, "size": size, "sha256": sha} for name, size, sha in MODEL_FILES
                ],
                "binary": binary_path(),
                "verified_at": time.time(),
            },
        )


_provisioners: dict[str, VlmProvisioner] = {}
_provisioner_lock = threading.Lock()


def get_provisioner(cfg: Any = None) -> VlmProvisioner:
    """One provisioner per data root, so app and tests never share wrong state."""
    key = str(cfg.root) if cfg is not None else ""
    with _provisioner_lock:
        if key not in _provisioners:
            _provisioners[key] = VlmProvisioner(cfg)
        return _provisioners[key]
