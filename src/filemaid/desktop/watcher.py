"""Vigilancia de una carpeta elegida: un único sondeo, sin ejecutar extracción.

El vigilante no procesa nada por sí mismo. Detecta ficheros PDF *estables* en la
carpeta seleccionada y los entrega a la MISMA ruta de ingestión que usa el
worker (`filemaid.ingest.get_ingestion(cfg).submit`), que los encola en su único
procesador acotado. Así no se duplica el flujo del pipeline ni se añade
paralelismo de extracción/VLM sobre trabajos compartidos.

La finalización se observa por estado del job; la notificación de disputa se
dispara solo con el resultado final `ESCALAR` y su procedencia se guarda en
`_local/watch-notified` únicamente después de un intento de entrega nativa
aceptado por el sistema operativo.

Estado en PouchDB `_local/*` (nunca ficheros JSON):

- `_local/watch-settings`: `{folder, enabled}` (local, no replicado).
- `_local/watch-dedup`: `{"<json [folder, name]>": "<sha256>"}`; acotado por
  carpeta para que cambiar de carpeta con el mismo nombre base no omita una
  importación requerida.
- `_local/watch-notified`: `{"<decision_id>": <timestamp>}`.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path

from filemaid.extract.cache import sha256_file
from filemaid.store.pouch import PouchStore, file_key

log = logging.getLogger(__name__)

SETTINGS_ID = "watch-settings"
DEDUP_ID = "watch-dedup"
NOTIFIED_ID = "watch-notified"

_POLL_S = 1.0
_SETTLE_POLLS = 2
_RECONCILE_S = 60.0
_RETRY_NOTIF_S = 30.0
_TEMP_SUFFIXES = {".tmp", ".part", ".crdownload", ".download", ".partial"}


def _es_pdf(path: Path) -> bool:
    return path.suffix.lower() == ".pdf"


def _es_temporal(name: str) -> bool:
    return name.startswith((".", "~$")) or Path(name).suffix.lower() in _TEMP_SUFFIXES


def _clave(folder: str, name: str) -> str:
    return json.dumps([folder, name], ensure_ascii=False)


def _pdf_completo(path: Path) -> bool:
    """Validación estructural: cabecera `%PDF-` y tráiler `%%EOF`.

    Un PDF truncado (copia aún en curso) no se encola; el sondeo lo reintenta
    cuando la firma (tamaño+mtime) cambie.
    """
    try:
        with path.open("rb") as f:
            if b"%PDF-" not in f.read(1024):
                return False
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - 4096))
            return b"%%EOF" in f.read()
    except OSError:
        return False


class Watcher:
    """Un hilo de sondeo; entrega a la cola de ingestión compartida."""

    def __init__(
        self,
        cfg,
        notificador,
        *,
        servicio=None,
        poll_s: float = _POLL_S,
        settle_polls: int = _SETTLE_POLLS,
        reconcile_s: float = _RECONCILE_S,
    ) -> None:
        self.cfg = cfg
        self.store = PouchStore(cfg.root)
        self._notificador = notificador
        self._servicio = servicio
        self._poll_s = poll_s
        self._settle = max(1, settle_polls)
        self._reconcile_s = reconcile_s
        self._lock = threading.Lock()
        self._scan_lock = threading.Lock()
        self._stop = threading.Event()
        self._cerrado = False
        self._hilo: threading.Thread | None = None
        self._folder = ""
        self._enabled = False
        self._error = ""
        self._processed = 0
        self._estables: dict[str, tuple[tuple[int, int], int]] = {}
        self._resueltos: dict[str, tuple[int, int]] = {}
        self._dedup: dict[str, str] = {}
        self._notificado: dict[str, float] = {}
        self._jobs: dict[str, dict] = {}
        self._pendientes: set[str] = set()
        self._intento: dict[str, float] = {}
        self._proximo_reconcile = 0.0
        self._cargar()

    # -- estado persistido -------------------------------------------------

    def _cargar(self) -> None:
        ajustes = self.store.local_get(SETTINGS_ID) or {}
        self._folder = str(ajustes.get("folder", "") or "")
        self._enabled = bool(ajustes.get("enabled", False))
        self._dedup = dict(self.store.local_get(DEDUP_ID) or {})
        self._notificado = dict(self.store.local_get(NOTIFIED_ID) or {})
        self._pendientes = {k for k in self._dedup if self._carpeta_de(k) == self._folder}

    @staticmethod
    def _carpeta_de(clave: str) -> str:
        try:
            carpeta, _ = json.loads(clave)
        except (ValueError, TypeError):
            return ""
        return carpeta if isinstance(carpeta, str) else ""

    # -- ciclo de vida -----------------------------------------------------

    def start(self) -> None:
        with self._lock:
            if self._cerrado:
                return
            if self._hilo is not None and self._hilo.is_alive():
                return
            self._stop.clear()
            self._hilo = threading.Thread(target=self._bucle, name="filemaid-watcher", daemon=True)
            hilo = self._hilo
        hilo.start()

    def stop(self) -> None:
        """Detiene el sondeo y prohíbe nuevos envíos. Idempotente y acotado."""
        with self._lock:
            self._cerrado = True
            self._stop.set()
            hilo = self._hilo
        self._unir(hilo)

    def _pausar(self) -> None:
        with self._lock:
            self._stop.set()
            hilo = self._hilo
        self._unir(hilo)

    @staticmethod
    def _unir(hilo: threading.Thread | None) -> None:
        if hilo is not None and hilo.is_alive() and hilo is not threading.current_thread():
            hilo.join(timeout=5.0)

    def configurar(self, folder: str, enabled: bool) -> dict:
        """Valida y persiste la selección; arranca o pausa el sondeo."""
        folder = (folder or "").strip()
        if enabled:
            if not folder:
                raise ValueError("seleccione una carpeta para vigilar")
            ruta = Path(folder).expanduser()
            if not ruta.is_dir():
                raise ValueError(f"la carpeta no existe o no es un directorio: {folder}")
            try:
                next(ruta.iterdir(), None)
            except OSError as exc:
                raise ValueError(f"la carpeta no se puede leer: {exc}") from exc
            folder = str(ruta.resolve())
        self.store.local_put(SETTINGS_ID, {"folder": folder, "enabled": bool(enabled)})
        with self._lock:
            cambio = folder != self._folder
            self._folder = folder
            self._enabled = bool(enabled)
            self._error = ""
            if cambio:
                self._estables.clear()
                self._resueltos.clear()
                self._jobs.clear()
                self._pendientes = {
                    k for k in self._dedup if self._carpeta_de(k) == self._folder
                }
                self._proximo_reconcile = 0.0
        if enabled:
            self.start()
        else:
            self._pausar()
        return self.estado()

    def escanear(self) -> dict:
        """Un sondeo inmediato de la carpeta elegida (aplica el dedup)."""
        with self._lock:
            activo = self._enabled
        if activo:
            self._escanear_una_vez()
        return self.estado()

    def estado(self) -> dict:
        with self._lock:
            return {
                "enabled": self._enabled,
                "folder": self._folder,
                "running": self._hilo is not None and self._hilo.is_alive(),
                "error": self._error,
                "processed": self._processed,
                "pending": len(self._pendientes) + len(self._jobs),
                "notifications": self._notificador.estado(),
            }

    # -- sondeo ------------------------------------------------------------

    def _bucle(self) -> None:
        while not self._stop.is_set():
            try:
                with self._lock:
                    activo = self._enabled
                if activo:
                    self._escanear_una_vez()
            except Exception as exc:
                log.exception("fallo del vigilante")
                with self._lock:
                    self._error = f"{type(exc).__name__}: {exc}"
            self._stop.wait(self._poll_s)

    def _escanear_una_vez(self) -> None:
        if not self._scan_lock.acquire(blocking=False):
            return
        try:
            with self._lock:
                folder = self._folder
            if not folder:
                return
            try:
                entradas = list(Path(folder).iterdir())
            except OSError as exc:
                with self._lock:
                    self._error = f"no se puede leer la carpeta: {exc}"
                return
            for entrada in entradas:
                if self._stop.is_set():
                    return
                if not self._candidato(entrada):
                    continue
                self._evaluar(entrada)
            self._resolver_jobs()
            self._resolver_pendientes()
        finally:
            self._scan_lock.release()

    @staticmethod
    def _candidato(path: Path) -> bool:
        if path.is_symlink() or not path.is_file():
            return False
        if not _es_pdf(path):
            return False
        return not _es_temporal(path.name)

    def _evaluar(self, path: Path) -> None:
        try:
            st = path.stat()
        except OSError:
            return
        firma = (st.st_size, st.st_mtime_ns)
        with self._lock:
            if self._resueltos.get(path.name) == firma:
                return
            previo = self._estables.get(path.name)
            if previo is None or previo[0] != firma:
                self._estables[path.name] = (firma, 1)
                return
            cuenta = previo[1] + 1
            self._estables[path.name] = (firma, cuenta)
            if cuenta < self._settle:
                return
            folder = self._folder
        if not _pdf_completo(path):
            # Copia en curso o PDF truncado: no se encola; se reintenta si cambia.
            self._marcar_rechazado(path.name, firma)
            return
        try:
            sha = sha256_file(path)
        except OSError as exc:
            with self._lock:
                self._error = f"no se pudo leer {path.name}: {exc}"
            return
        clave = _clave(folder, path.name)
        with self._lock:
            if self._dedup.get(clave) == sha:
                self._resueltos[path.name] = firma
                self._estables.pop(path.name, None)
                return
        if self._stop.is_set():
            return
        self._entregar(path, folder, clave, sha, firma)

    def _entregar(
        self, path: Path, folder: str, clave: str, sha: str, firma: tuple[int, int]
    ) -> None:
        try:
            key = file_key(path.name, sha)
            if self.store.get(f"file:{key}") is not None:
                # Ya escaneado en una ejecución anterior (carrera de cierre).
                self._marcar_resuelto(clave, path.name, sha, firma)
                return
            res = self._svc().submit([(path.name, str(path))], origin="watcher")
        except ValueError as exc:
            # Rechazo de validación: no se marca dedup; se reintenta si cambia.
            log.warning("ingestión rechazada para %s: %s", path.name, exc)
            self._marcar_rechazado(path.name, firma)
            with self._lock:
                self._error = f"{path.name}: {exc}"
            return
        except Exception as exc:
            # Fallo transitorio: reintentar en el siguiente sondeo.
            log.warning("no se pudo encolar %s: %s", path.name, exc)
            with self._lock:
                self._error = f"no se pudo encolar {path.name}: {exc}"
            return
        rechazados = res.get("rejected") or []
        aceptados = res.get("accepted") or []
        if rechazados:
            motivo = rechazados[0].get("reason", "rechazado")
            log.warning("ingestión rechazada para %s: %s", path.name, motivo)
            self._marcar_rechazado(path.name, firma)
            with self._lock:
                self._error = f"{path.name}: {motivo}"
            return
        if not aceptados:
            with self._lock:
                self._error = f"{path.name}: la ingestión no aceptó el fichero"
            return
        item = aceptados[0]
        with self._lock:
            self._dedup[clave] = sha
            self._resueltos[path.name] = firma
            self._estables.pop(path.name, None)
            self._processed += 1
            self._error = ""
            self._jobs[res["job_id"]] = {
                "folder": folder,
                "items": {item["file_key"]: (path.name, clave)},
            }
        self._guardar_dedup()

    def _marcar_resuelto(
        self, clave: str, name: str, sha: str, firma: tuple[int, int]
    ) -> None:
        with self._lock:
            self._dedup[clave] = sha
            self._resueltos[name] = firma
            self._estables.pop(name, None)
        self._guardar_dedup()

    def _marcar_rechazado(self, name: str, firma: tuple[int, int]) -> None:
        """Rechazo: no se marca dedup; se reintenta cuando el fichero cambie."""
        with self._lock:
            self._resueltos[name] = firma
            self._estables.pop(name, None)

    def _guardar_dedup(self) -> None:
        with self._lock:
            datos = dict(self._dedup)
        self.store.local_put(DEDUP_ID, datos)

    # -- finalización y notificación --------------------------------------

    def _resolver_jobs(self) -> None:
        with self._lock:
            jobs = dict(self._jobs)
        for job_id, info in jobs.items():
            try:
                st = self._svc().status(job_id)
            except Exception as exc:
                log.warning("no se pudo consultar el job %s: %s", job_id, exc)
                continue
            if st.get("state") not in {"complete", "failed"}:
                continue
            for item in st.get("items", []):
                entrada = info["items"].get(item.get("file_key"))
                nombre = entrada[0] if entrada else item.get("file_id")
                if item.get("status") == "error":
                    with self._lock:
                        self._error = (
                            f"{nombre}: {item.get('error') or 'fallo de procesamiento'}"
                        )
                    continue
                if item.get("result") == "ESCALAR":
                    notificado = self._notificar_disputa(item.get("decision_id"), nombre)
                else:
                    notificado = True
                if entrada is None:
                    continue
                with self._lock:
                    if notificado:
                        self._pendientes.discard(entrada[1])
                    else:
                        # Entrega nativa fallida: conservar la clave para que
                        # la reconciliación reintente en esta misma sesión.
                        self._pendientes.add(entrada[1])
            with self._lock:
                self._jobs.pop(job_id, None)

    def _resolver_pendientes(self) -> None:
        """Reconciliación acotada por carpeta (reinicio y reintentos)."""
        with self._lock:
            if not self._pendientes:
                return
            if time.monotonic() < self._proximo_reconcile:
                return
            self._proximo_reconcile = time.monotonic() + self._reconcile_s
            pendientes = set(self._pendientes)
            folder = self._folder
            dedup = dict(self._dedup)
        decisiones = self.store.list("decision:")
        ultima: dict[str, dict] = {}
        for d in decisiones:
            k = d.get("file_key")
            if not k:
                continue
            previo = ultima.get(k)
            if previo is None or d.get("timestamp", 0) > previo.get("timestamp", 0):
                ultima[k] = d
        for clave in pendientes:
            try:
                carpeta, name = json.loads(clave)
            except (ValueError, TypeError):
                continue
            if carpeta != folder:
                continue
            sha = dedup.get(clave)
            if not sha:
                continue
            d = ultima.get(file_key(name, sha))
            if d is None:
                continue
            resultado = d.get("result") or (d.get("decision") or {}).get("result")
            if resultado is None:
                continue
            if resultado == "ESCALAR":
                if self._notificar_disputa(d.get("_id"), name):
                    with self._lock:
                        self._pendientes.discard(clave)
            else:
                with self._lock:
                    self._pendientes.discard(clave)

    def _notificar_disputa(self, decision_id: str | None, name: str) -> bool:
        if not decision_id:
            return False
        with self._lock:
            if decision_id in self._notificado:
                return True
            if time.monotonic() - self._intento.get(decision_id, 0.0) < _RETRY_NOTIF_S:
                return False
            self._intento[decision_id] = time.monotonic()
        ok = self._notificador.notificar(
            "Factura en disputa", f"{name}: requiere revisión (ESCALAR)"
        )
        if not ok:
            with self._lock:
                self._error = (
                    "no se pudo mostrar la notificación nativa; "
                    "revise la bandeja del sistema"
                )
            return False
        with self._lock:
            self._notificado[decision_id] = time.time()
            datos = dict(self._notificado)
        self.store.local_put(NOTIFIED_ID, datos)
        return True

    def _svc(self):
        if self._servicio is None:
            from filemaid.ingest import get_ingestion

            self._servicio = get_ingestion(self.cfg)
        return self._servicio
