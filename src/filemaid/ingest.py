"""Ingesta asíncrona: subidas/watcher → cola durable PouchDB → pipeline.

La API local (FastAPI) es el servicio de procesamiento compartido por la web y
el escritorio. Los ficheros se transmiten a una caché transitoria bajo
``FILEMAID_DATA/work`` (nunca /tmp) y el original se persiste en PouchDB como
artefacto **antes** de acusar recibo, de modo que un crash siempre puede
restaurar la entrada. La evidencia (scan, features, fields, decisión,
artefactos) vive en PouchDB; las copias transitorias de subida/render/trabajo se
eliminan cuando el item es terminal. Los originales del cliente (watcher) nunca
se borran: se copian a la caché y solo se elimina la copia.

El staging nunca usa la ruta relativa del cliente como ruta del sistema: cada
fichero se aísla en su propio directorio UUID y el basename exacto (``file_id``)
se conserva como metadato, evitando colisiones de rutas anidadas, nombres
reservados de Windows y flujos alternativos (ADS).

Ninguna ruta de un documento PouchDB (que puede llegar por replicación) se usa
para leer o borrar: el workspace se deriva de ``jobs_dir`` + ``job_id`` válido y
el hijo de staging se valida como ``<uuid>/<file_id>`` exacto.

Varios procesos pueden compartir el mismo ``FILEMAID_DATA`` (app nativa y
``filemaid serve``): cada trabajo se reclama con un lock de fichero
interproceso no bloqueante, de modo que solo un proceso lo procesa.
"""

from __future__ import annotations

import contextlib
import logging
import mimetypes
import os
import queue
import re
import shutil
import threading
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from python_multipart import MultipartParser
from python_multipart.multipart import parse_options_header

from .config import AppConfig
from .extract.cache import sha256_file
from .extract.ladder import IMAGE_SUFFIXES
from .pipeline import Pipeline
from .store.pouch import PouchStore, file_key

if os.name == "nt":  # Windows: no fcntl; lock one byte via the CRT
    import msvcrt

    def _try_lock(handle: Any) -> bool:
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(handle: Any) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _try_lock(handle: Any) -> bool:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(handle: Any) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)


_SUPPORTED_SUFFIXES = {".pdf"} | IMAGE_SUFFIXES
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_HEADER_COUNT = 8
MAX_HEADER_SIZE = 4224
_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
}
_DRIVE = re.compile(r"^[A-Za-z]:")
_JOB_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_UUID_HEX = re.compile(r"^[0-9a-f]{32}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_WINDOWS_RESERVED = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class UploadTooLarge(ValueError):
    """La petición excede el tamaño agregado permitido (HTTP 413)."""


def safe_rel_path(filename: str) -> str:
    """Valida una ruta relativa no confiable y la devuelve con separadores '/'.

    Rechaza rutas absolutas, letras de unidad, ``..`` y componentes vacíos. El
    basename se conserva exacto; solo se normalizan los separadores.
    """
    raw = filename.replace("\\", "/")
    if not raw or raw.endswith("/"):
        raise ValueError("ruta vacía")
    if raw.startswith("/") or _DRIVE.match(raw):
        raise ValueError("ruta absoluta no permitida")
    parts = raw.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("ruta relativa inválida")
    if any(any(ord(ch) < 32 for ch in part) for part in parts):
        raise ValueError("ruta con caracteres de control")
    return "/".join(parts)


def safe_file_id(name: str) -> str:
    """Valida el basename exacto (``file_id``) sin normalizarlo nunca.

    Rechaza separadores, ``:`` (ADS), punto/espacio final y nombres reservados
    de Windows, que no se pueden materializar de forma portable en disco.
    """
    if not name or name in {".", ".."}:
        raise ValueError("nombre de fichero inválido")
    if "/" in name or "\\" in name:
        raise ValueError("el nombre no puede contener separadores")
    if any(ord(ch) < 32 for ch in name):
        raise ValueError("nombre con caracteres de control")
    if ":" in name:
        raise ValueError("nombre con ':' no permitido")
    if name[-1] in {".", " "}:
        raise ValueError("nombre con punto o espacio final no permitido")
    if name.split(".")[0].upper() in _WINDOWS_RESERVED:
        raise ValueError(f"nombre reservado en Windows: {name}")
    return name


def _check_magic(path: Path, suffix: str) -> None:
    """Puerta barata de cabecera; la validez real la decide el pipeline."""
    prefixes = _MAGIC.get(suffix)
    if prefixes is None:
        return
    with path.open("rb") as handle:
        head = handle.read(16)
    if not any(head.startswith(prefix) for prefix in prefixes):
        raise ValueError(f"el contenido no coincide con la extensión {suffix}")


def _boundary(content_type: str) -> bytes:
    if "multipart/form-data" not in content_type.lower():
        raise ValueError("se requiere multipart/form-data")
    _, options = parse_options_header(content_type.encode("latin-1"))
    boundary = options.get(b"boundary")
    if not boundary:
        raise ValueError("falta el boundary multipart")
    return boundary


class _UploadSink:
    """Escribe cada parte ``files`` a un directorio UUID (nunca /tmp)."""

    def __init__(self, dest_dir: Path, max_file_bytes: int) -> None:
        self.dest_dir = dest_dir
        self.max_file_bytes = max_file_bytes
        self.staged: list[dict[str, Any]] = []
        self.rejected: list[dict[str, str]] = []
        self.ended = False
        self._field = bytearray()
        self._value = bytearray()
        self._headers: dict[bytes, bytes] = {}
        self._handle = None
        self._path: Path | None = None
        self._rel: str | None = None
        self._file_id: str | None = None
        self._size = 0
        self._seen: set[str] = set()

    def callbacks(self) -> dict[str, Callable[..., Any]]:
        return {
            "on_part_begin": self.on_part_begin,
            "on_header_field": self.on_header_field,
            "on_header_value": self.on_header_value,
            "on_header_end": self.on_header_end,
            "on_headers_finished": self.on_headers_finished,
            "on_part_data": self.on_part_data,
            "on_part_end": self.on_part_end,
            "on_end": self.on_end,
        }

    def on_part_begin(self) -> None:
        self._headers = {}
        self._field = bytearray()
        self._value = bytearray()
        self._handle = None
        self._path = None
        self._rel = None
        self._file_id = None
        self._size = 0

    def on_header_field(self, data: bytes, start: int, end: int) -> None:
        self._field += data[start:end]

    def on_header_value(self, data: bytes, start: int, end: int) -> None:
        self._value += data[start:end]

    def on_header_end(self) -> None:
        self._headers[bytes(self._field).lower()] = bytes(self._value)
        self._field = bytearray()
        self._value = bytearray()

    def on_headers_finished(self) -> None:
        _, options = parse_options_header(self._headers.get(b"content-disposition", b""))
        if options.get(b"name") != b"files":
            return
        raw = options.get(b"filename", b"")
        if not raw:
            return
        try:
            filename = raw.decode("utf-8")
        except UnicodeDecodeError:
            self.rejected.append(
                {"rel_path": raw.decode("utf-8", "replace"), "reason": "nombre no UTF-8"}
            )
            return
        try:
            rel = safe_rel_path(filename)
            file_id = safe_file_id(PurePosixPath(rel).name)
        except ValueError as exc:
            self.rejected.append({"rel_path": filename, "reason": str(exc)})
            return
        if rel in self._seen:
            self.rejected.append(
                {"rel_path": rel, "reason": "ruta relativa duplicada en la petición"}
            )
            return
        self._seen.add(rel)
        suffix = PurePosixPath(file_id).suffix.lower()
        if suffix not in _SUPPORTED_SUFFIXES:
            self.rejected.append(
                {"rel_path": rel, "reason": f"extensión no soportada: {suffix or file_id}"}
            )
            return
        path = self.dest_dir / uuid.uuid4().hex / file_id
        path.parent.mkdir(parents=True, exist_ok=True)
        self._rel = rel
        self._file_id = file_id
        self._path = path
        self._handle = path.open("wb")

    def on_part_data(self, data: bytes, start: int, end: int) -> None:
        if self._handle is None:
            return
        chunk = data[start:end]
        self._size += len(chunk)
        if self._size > self.max_file_bytes:
            self._discard(f"fichero demasiado grande (> {self.max_file_bytes} bytes)")
            return
        self._handle.write(chunk)

    def on_part_end(self) -> None:
        if self._handle is None:
            return
        self._handle.close()
        self._handle = None
        assert self._rel is not None and self._path is not None and self._file_id is not None
        self.staged.append(
            {
                "rel_path": self._rel,
                "file_id": self._file_id,
                "path": self._path,
                "size": self._size,
            }
        )
        self._rel = None
        self._file_id = None
        self._path = None

    def on_end(self) -> None:
        self.ended = True

    def close(self) -> None:
        """Cierra el fichero activo (multipart truncado o excepción del parser)."""
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def _discard(self, reason: str) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if self._path is not None:
            self._path.unlink(missing_ok=True)
        if self._rel is not None:
            self.rejected.append({"rel_path": self._rel, "reason": reason})
        self._rel = None
        self._file_id = None
        self._path = None


async def stream_uploads(
    chunks: AsyncIterator[bytes],
    content_type: str,
    dest_dir: Path,
    *,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> dict[str, Any]:
    """Transmite las partes ``files`` a ``dest_dir`` sin bufferizar en /tmp.

    Cuenta **todos** los bytes del cuerpo (incluidas partes descartadas y
    cabeceras) contra ``max_total_bytes``. Devuelve
    ``{"staged": [{"rel_path", "file_id", "path", "size"}], "rejected": [...]}``.
    Lanza ``UploadTooLarge`` si excede el total y ``ValueError`` si el cuerpo no
    es multipart o está truncado.
    """
    boundary = _boundary(content_type)
    sink = _UploadSink(dest_dir, max_file_bytes)
    parser = MultipartParser(
        boundary,
        sink.callbacks(),
        max_header_count=MAX_HEADER_COUNT,
        max_header_size=MAX_HEADER_SIZE,
    )
    total = 0
    try:
        async for chunk in chunks:
            total += len(chunk)
            if total > max_total_bytes:
                raise UploadTooLarge(f"subida demasiado grande (> {max_total_bytes} bytes)")
            parser.write(chunk)
        parser.finalize()
    except UploadTooLarge:
        raise
    except Exception as exc:
        raise ValueError(f"cuerpo multipart inválido: {exc}") from exc
    finally:
        sink.close()
    if not sink.ended:
        raise ValueError("cuerpo multipart incompleto")
    return {"staged": sink.staged, "rejected": sink.rejected}


class _JobClaim:
    """Reclama un trabajo con un lock de fichero interproceso no bloqueante."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        if not _try_lock(handle):
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            with contextlib.suppress(OSError):
                _unlock(self._handle)
            self._handle.close()
            self._handle = None


class IngestionService:
    """Cola durable de trabajos de ingesta, procesados por un único worker."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self.store = PouchStore(cfg.root)
        self.jobs_dir = cfg.root / "work" / "jobs"
        self._queue: queue.Queue[str] = queue.Queue()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._worker: threading.Thread | None = None

    # -- API pública ------------------------------------------------------

    def start(self) -> None:
        """Reanuda el servicio tras un ``stop`` (solo si el worker ya terminó)."""
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            self._stop.clear()

    def submit(
        self,
        entries: Sequence[tuple[str, Path]],
        origin: str = "upload",
        *,
        move: bool = False,
    ) -> dict[str, Any]:
        """Persiste entrada + trabajo en PouchDB y encola; devuelve el job_id.

        ``entries`` son pares ``(ruta_relativa, ruta_origen)``. El original se
        persiste como artefacto PouchDB antes de acusar recibo; ``move=True``
        mueve los ficheros ya staged (subida HTTP) en lugar de copiarlos.
        """
        pairs = [(str(rel), Path(src)) for rel, src in entries]
        if not pairs:
            raise ValueError("no hay ficheros que ingerir")
        job_id = str(uuid.uuid4())
        job_dir = self.jobs_dir / job_id
        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, str]] = []
        staged: list[tuple[str, str, Path, str]] = []
        seen_paths: set[str] = set()
        seen_keys: set[str] = set()
        for rel_raw, source in pairs:
            try:
                rel = safe_rel_path(rel_raw)
                file_id = safe_file_id(PurePosixPath(rel).name)
            except ValueError as exc:
                rejected.append({"rel_path": rel_raw, "reason": str(exc)})
                continue
            if rel in seen_paths:
                rejected.append(
                    {"rel_path": rel, "reason": "ruta relativa duplicada en la petición"}
                )
                continue
            seen_paths.add(rel)
            try:
                if not source.is_file():
                    raise ValueError("fichero no encontrado")
                size = source.stat().st_size
                if size > MAX_FILE_BYTES:
                    raise ValueError(f"fichero demasiado grande ({size} bytes)")
                suffix = PurePosixPath(file_id).suffix.lower()
                if suffix not in _SUPPORTED_SUFFIXES:
                    raise ValueError(f"extensión no soportada: {suffix or file_id}")
                _check_magic(source, suffix)
                sha = sha256_file(source)
            except (ValueError, OSError) as exc:
                rejected.append({"rel_path": rel, "reason": str(exc)})
                continue
            key = file_key(file_id, sha)
            if key in seen_keys:
                rejected.append(
                    {
                        "rel_path": rel,
                        "reason": "identidad duplicada: mismo nombre y contenido",
                    }
                )
                continue
            seen_keys.add(key)
            staged.append((rel, file_id, source, sha))

        if not staged:
            detail = "; ".join(item["reason"] for item in rejected) or "sin ficheros"
            raise ValueError(f"ningún fichero válido: {detail}")

        job_dir.mkdir(parents=True, exist_ok=True)
        expected: list[dict[str, Any]] = []
        for rel, file_id, source, sha in staged:
            child = uuid.uuid4().hex
            dest = job_dir / child / file_id
            dest.parent.mkdir(parents=True, exist_ok=True)
            if move:
                os.replace(source, dest)
            else:
                shutil.copyfile(source, dest)
            if sha256_file(dest) != sha:
                raise RuntimeError(f"el fichero cambió durante la ingesta: {rel}")
            artifact_id = self.store.artifact(
                {"scan_id": f"job-{job_id}", "job_id": job_id},
                "job_input",
                file_id,
                dest,
                mimetypes.guess_type(file_id)[0] or "application/octet-stream",
            )
            key = file_key(file_id, sha)
            expected.append(
                {
                    "file_id": file_id,
                    "sha256": sha,
                    "file_key": key,
                    "artifact_id": artifact_id,
                    "staged": f"{child}/{file_id}",
                }
            )
            accepted.append({"file_id": file_id, "file_key": key, "sha256": sha, "rel_path": rel})
        expected.sort(key=lambda item: (item["file_id"], item["sha256"]))
        self.store.put(
            {
                "_id": f"job:{job_id}",
                "kind": "job",
                "job_id": job_id,
                "origin": origin,
                "expected": expected,
                "created_at": time.time(),
            }
        )
        self._enqueue(job_id)
        return {"job_id": job_id, "accepted": accepted, "rejected": rejected}

    def status(self, job_id: str) -> dict[str, Any] | None:
        job = self.store.get(f"job:{job_id}")
        if job is None or job.get("kind") != "job":
            return None
        result = self.store.get(f"job_result:{job_id}")
        items = {doc["file_key"]: doc for doc in self.store.list(f"job_item:{job_id}:")}
        events = self.store.list(f"job_event:{job_id}:")
        started = any(event.get("type") == "job_started" for event in events)
        worker_error = next(
            (event for event in reversed(events) if event.get("type") == "worker_error"), None
        )
        rows: list[dict[str, Any]] = []
        done = error = 0
        for entry in job.get("expected", []):
            item = items.get(entry.get("file_key"))
            if item is None:
                rows.append(
                    {
                        "file_id": entry.get("file_id"),
                        "file_key": entry.get("file_key"),
                        "sha256": entry.get("sha256"),
                        "status": "pending",
                        "result": None,
                        "decision_id": None,
                        "scan_id": None,
                        "error": None,
                        "updated_at": None,
                    }
                )
                continue
            if item["status"] == "done":
                done += 1
            else:
                error += 1
            rows.append(
                {
                    "file_id": item["file_id"],
                    "file_key": item["file_key"],
                    "sha256": item["sha256"],
                    "status": item["status"],
                    "result": item.get("result"),
                    "decision_id": item.get("decision_id"),
                    "scan_id": item.get("scan_id"),
                    "error": item.get("error"),
                    "updated_at": item.get("timestamp"),
                }
            )
        total = len(job.get("expected", []))
        state = result["status"] if result else ("running" if started else "queued")
        return {
            "job_id": job_id,
            "origin": job.get("origin", "upload"),
            "state": state,
            "created_at": job.get("created_at"),
            "finished_at": result.get("finished_at") if result else None,
            "error": worker_error.get("error") if worker_error and result is None else None,
            "counts": {
                "total": total,
                "done": done,
                "error": error,
                "pending": total - done - error,
            },
            "items": rows,
        }

    def list_jobs(self) -> dict[str, Any]:
        jobs = [doc for doc in self.store.list("job:") if doc.get("kind") == "job"]
        jobs.sort(key=lambda doc: (doc.get("created_at", 0), doc.get("_id", "")), reverse=True)
        summaries: list[dict[str, Any]] = []
        for job in jobs:
            state = self.status(job["job_id"])
            if state is None:
                continue
            summaries.append(
                {
                    "job_id": state["job_id"],
                    "origin": state["origin"],
                    "state": state["state"],
                    "created_at": state["created_at"],
                    "finished_at": state["finished_at"],
                    **state["counts"],
                }
            )
        return {"jobs": summaries}

    def resume(self) -> None:
        """Reencola los trabajos sin resultado terminal (reanudación tras crash)."""
        for doc in self.store.list("job:"):
            if doc.get("kind") != "job":
                continue
            job_id = doc.get("job_id")
            if not isinstance(job_id, str) or not _JOB_ID.match(job_id):
                continue
            if self.store.get(f"job_result:{job_id}") is None:
                self._enqueue(job_id)

    def stop(self, timeout: float = 4.0) -> None:
        """Parada cooperativa: el worker termina el item en vuelo y sale."""
        self._stop.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=timeout)

    # -- worker -----------------------------------------------------------

    def _enqueue(self, job_id: str) -> None:
        self._ensure_worker()
        self._queue.put(job_id)

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._worker_loop, name="filemaid-ingest", daemon=True
                )
                self._worker.start()

    def _worker_loop(self) -> None:
        pipeline: Pipeline | None = None
        while not self._stop.is_set():
            try:
                job_id = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                # Pipeline init lives inside the try: a failure must not kill the
                # worker and leave jobs silently stuck as "running".
                if pipeline is None:
                    pipeline = Pipeline(self.cfg)
                self._process_job(pipeline, job_id)
            except Exception as exc:
                logging.getLogger(__name__).exception("trabajo de ingesta %s falló", job_id)
                with contextlib.suppress(Exception):
                    self._record_worker_error(job_id, exc)
            finally:
                self._queue.task_done()

    def _process_job(self, pipeline: Pipeline, job_id: str) -> None:
        if not _JOB_ID.match(job_id):
            return
        job = self.store.get(f"job:{job_id}")
        if job is None or job.get("kind") != "job":
            return
        if self.store.get(f"job_result:{job_id}") is not None:
            return
        claim = _JobClaim(self.jobs_dir / f"{job_id}.lock")
        if not claim.acquire():
            return  # otro proceso lo está procesando
        try:
            if self.store.get(f"job_result:{job_id}") is not None:
                return
            self._record_started(job_id)
            for entry in job.get("expected", []):
                if self._stop.is_set():
                    return
                if not isinstance(entry, dict):
                    continue
                if self.store.get(f"job_item:{job_id}:{entry.get('file_key')}") is not None:
                    continue
                self._process_item(pipeline, job_id, entry)
            self._finish_job(job_id, job)
        finally:
            claim.release()

    def _record_started(self, job_id: str) -> None:
        if any(doc.get("type") == "job_started" for doc in self.store.list(f"job_event:{job_id}:")):
            return
        self.store.put(
            {
                "_id": f"job_event:{job_id}:{uuid.uuid4()}",
                "kind": "job_event",
                "job_id": job_id,
                "type": "job_started",
                "timestamp": time.time(),
            }
        )

    def _process_item(self, pipeline: Pipeline, job_id: str, entry: dict) -> None:
        reason = self._entry_error(entry)
        if reason is not None:
            self._record_item(job_id, entry, status="error", error=reason)
            return
        restored: Path | None = None
        scan_id: str | None = None
        try:
            staged = self._staged_path(job_id, entry)
            source = staged if staged is not None and staged.is_file() else None
            if source is None:
                restored = self._restore(job_id, entry)
                source = restored
            decision = pipeline.process_pdf(source)
            scan_id = self._item_scan_id(pipeline, entry)
            decision_doc = self.store.get(f"decision:{scan_id}") if scan_id else None
            if decision_doc is None or decision_doc.get("file_key") != entry["file_key"]:
                raise RuntimeError("la decisión no corresponde al fichero procesado")
            self._record_item(
                job_id,
                entry,
                status="done",
                scan_id=scan_id,
                decision_id=f"decision:{scan_id}",
                result=decision.result.value,
            )
        except Exception as exc:
            scan_id = self._item_scan_id(pipeline, entry)
            self._record_item(job_id, entry, status="error", error=f"{type(exc).__name__}: {exc}")
        finally:
            if restored is not None:
                with contextlib.suppress(OSError):
                    restored.unlink(missing_ok=True)
                    restored.parent.rmdir()
            try:
                self._cleanup_item(job_id, entry, scan_id)
            except Exception as exc:
                # La limpieza nunca reescribe el resultado de dominio ya persistido.
                self._record_cleanup_error(job_id, entry, exc)

    def _entry_error(self, entry: dict) -> str | None:
        """Valida una entrada de ``expected`` (documento no confiable)."""
        file_id = entry.get("file_id")
        sha = entry.get("sha256")
        key = entry.get("file_key")
        artifact_id = entry.get("artifact_id")
        if not isinstance(file_id, str):
            return "entrada inválida: file_id ausente"
        try:
            safe_file_id(file_id)
        except ValueError as exc:
            return f"entrada inválida: {exc}"
        if not isinstance(sha, str) or not _SHA256.match(sha):
            return "entrada inválida: sha256"
        if not isinstance(key, str) or not _SHA256.match(key):
            return "entrada inválida: file_key"
        if not isinstance(artifact_id, str) or not artifact_id.startswith("artifact:"):
            return "entrada inválida: artifact_id"
        return None

    def _job_dir(self, job_id: str) -> Path | None:
        if not isinstance(job_id, str) or not _JOB_ID.match(job_id):
            return None
        return self.jobs_dir / job_id

    def _staged_path(self, job_id: str, entry: dict) -> Path | None:
        """Ruta de staging derivada y validada (nunca la del documento)."""
        job_dir = self._job_dir(job_id)
        rel = entry.get("staged")
        if job_dir is None or not isinstance(rel, str):
            return None
        parts = rel.split("/")
        if len(parts) != 2 or not _UUID_HEX.match(parts[0]) or parts[1] != entry.get("file_id"):
            return None
        path = job_dir / parts[0] / parts[1]
        if path.parent.parent != job_dir:
            return None
        return path

    def _item_scan_id(self, pipeline: Pipeline, entry: dict) -> str | None:
        """Scan realmente creado para este item (nunca el último global)."""
        scan_id = getattr(pipeline, "_last_scan_id", None)
        if not isinstance(scan_id, str) or not _JOB_ID.match(scan_id):
            return None
        if self.store.get(f"scan:{entry['file_key']}:{scan_id}") is None:
            return None
        return scan_id

    def _record_worker_error(self, job_id: str, exc: Exception) -> None:
        if not _JOB_ID.match(job_id):
            return
        self.store.put(
            {
                "_id": f"job_event:{job_id}:{uuid.uuid4()}",
                "kind": "job_event",
                "job_id": job_id,
                "type": "worker_error",
                "error": f"{type(exc).__name__}: {exc}",
                "timestamp": time.time(),
            }
        )

    def _record_cleanup_error(self, job_id: str, entry: dict, exc: Exception) -> None:
        self.store.put(
            {
                "_id": f"job_event:{job_id}:{uuid.uuid4()}",
                "kind": "job_event",
                "job_id": job_id,
                "type": "cleanup_error",
                "file_id": entry.get("file_id"),
                "file_key": entry.get("file_key"),
                "error": f"{type(exc).__name__}: {exc}",
                "timestamp": time.time(),
            }
        )

    def _restore(self, job_id: str, entry: dict) -> Path:
        """Restaura el original desde el artefacto PouchDB si la caché se perdió."""
        job_dir = self._job_dir(job_id)
        if job_dir is None:
            raise RuntimeError("job_id inválido")
        artifact = self.store.get(entry["artifact_id"])
        if (
            artifact is None
            or artifact.get("kind") != "artifact"
            or artifact.get("job_id") != job_id
        ):
            raise RuntimeError("artefacto de entrada inválido")
        dest = job_dir / "restore" / uuid.uuid4().hex / entry["file_id"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as handle:
            for chunk in self.store.read_artifact(entry["artifact_id"]):
                handle.write(chunk)
        return dest

    def _record_item(
        self,
        job_id: str,
        entry: dict,
        *,
        status: str,
        scan_id: str | None = None,
        decision_id: str | None = None,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        self.store.put(
            {
                "_id": f"job_item:{job_id}:{entry['file_key']}",
                "kind": "job_item",
                "job_id": job_id,
                "file_id": entry["file_id"],
                "file_key": entry["file_key"],
                "sha256": entry["sha256"],
                "status": status,
                "scan_id": scan_id,
                "decision_id": decision_id,
                "result": result,
                "error": error,
                "timestamp": time.time(),
            }
        )

    def _cleanup_item(self, job_id: str, entry: dict, scan_id: str | None) -> None:
        """Borra la caché transitoria cuando el item es terminal (evidencia en DB)."""
        staged = self._staged_path(job_id, entry)
        if staged is not None:
            staged.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                staged.parent.rmdir()
        if scan_id and _JOB_ID.match(scan_id):
            for target in (self.cfg.root / "scans" / scan_id, self.cfg.pages_dir / scan_id):
                if target.exists():
                    shutil.rmtree(target)

    def _finish_job(self, job_id: str, job: dict) -> None:
        items = self.store.list(f"job_item:{job_id}:")
        if len(items) < len(job.get("expected", [])):
            return
        errors = [item for item in items if item["status"] == "error"]
        done = [item for item in items if item["status"] == "done"]
        self.store.put(
            {
                "_id": f"job_result:{job_id}",
                "kind": "job_result",
                "job_id": job_id,
                "status": "failed" if errors else "complete",
                "counts": {
                    "total": len(job.get("expected", [])),
                    "done": len(done),
                    "error": len(errors),
                },
                "finished_at": time.time(),
            }
        )
        job_dir = self._job_dir(job_id)
        if job_dir is not None and job_dir.exists():
            try:
                shutil.rmtree(job_dir)
            except Exception as exc:
                self._record_cleanup_error(job_id, {}, exc)


_services: dict[str, IngestionService] = {}
_services_lock = threading.Lock()


def get_ingestion(cfg: AppConfig) -> IngestionService:
    """Servicio de ingesta único por ``FILEMAID_DATA`` (API y watcher comparten)."""
    key = str(cfg.root.resolve())
    with _services_lock:
        service = _services.get(key)
        if service is None:
            service = IngestionService(cfg)
            _services[key] = service
        else:
            service.start()
        return service
