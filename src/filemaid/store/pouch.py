"""Local JS PouchDB, with one resident Node bridge per store root."""

from __future__ import annotations

import atexit
import base64
import collections
import contextlib
import errno
import hashlib
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

if os.name == "nt":  # Windows: no fcntl; lock one byte via the CRT
    import msvcrt

    def _lock_file(handle: Any) -> None:
        deadline = time.monotonic() + 300.0
        while True:
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                return
            except OSError as exc:
                # Only genuine contention is retried; anything else is a real error.
                if exc.errno not in (errno.EACCES, errno.EDEADLOCK):
                    raise
                if time.monotonic() >= deadline:
                    raise TimeoutError("could not acquire PouchDB lock") from exc
                time.sleep(0.1)

    def _unlock_file(handle: Any) -> None:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(handle: Any) -> None:
        fcntl.flock(handle, fcntl.LOCK_EX)

    def _unlock_file(handle: Any) -> None:
        fcntl.flock(handle, fcntl.LOCK_UN)

CHUNK_SIZE = 1024 * 1024
INLINE_LIMIT = 256 * 1024
BRIDGE = Path(__file__).with_name("pouchdb") / "bridge.mjs"
REQUEST_TIMEOUT_S = 120.0  # a single operation on the resident bridge
BRIDGE_IDLE_S = 30.0  # an unused bridge is retired (a resident node holds ~100 MB)
BRIDGE_GRACE_S = 5.0  # a bridge asked to stop gets this long before it is killed


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")


def file_key(file_id: str, sha256: str) -> str:
    return hashlib.sha256(canonical([file_id, sha256])).hexdigest()


def _verify_chunk(chunk_id: str, data: bytes) -> None:
    if hashlib.sha256(data).hexdigest() != chunk_id.removeprefix("blob:"):
        raise RuntimeError("PouchDB attachment checksum mismatch")


def _verify_artifact(doc: dict, chunks: list[bytes]) -> None:
    """Raise unless ``chunks`` are exactly the artifact's recorded content."""
    sha = hashlib.sha256()
    size = 0
    for chunk_id, data in zip(doc["chunks"], chunks, strict=True):
        _verify_chunk(chunk_id, data)
        sha.update(data)
        size += len(data)
    if size != doc["size"] or sha.hexdigest() != doc["sha256"]:
        raise RuntimeError("PouchDB artifact checksum mismatch")


def _close_pipes(proc: subprocess.Popen) -> None:
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is not None:
            with contextlib.suppress(OSError, ValueError):
                stream.close()


@contextlib.contextmanager
def interprocess_lock(path: Path):
    """Cross-process lock on a dedicated file (never the store lock itself).

    Used to serialise a multi-step operation (e.g. a review resolution) without
    holding the store lock across the whole pipeline, which would deadlock.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        _lock_file(handle)
        try:
            yield
        finally:
            _unlock_file(handle)


def couchdb_url(value: str) -> str:
    value = value.strip().rstrip("/")
    parsed = urlsplit(value)
    name = unquote(parsed.path.rsplit("/", 1)[-1])
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not name
        or name.startswith("_")
        or "/" in name
    ):
        raise ValueError("Se requiere la URL HTTP(S) de una base CouchDB sin credenciales")
    _ = parsed.port
    return value


class _BridgeGone(RuntimeError):
    """The resident bridge died or stopped answering; the request may be replayed."""


class _Bridge:
    """One resident ``node bridge.mjs <root>`` child, shared per store root.

    A fresh node process costs ~200 ms before it can answer, so one is started
    lazily per root and kept warm at ~6 ms per exchange. The child opens the
    LevelDB directory per exchange and closes it before answering (see
    bridge.mjs): LevelDB locks that directory for as long as any process keeps
    it open, so the lock file can still serialise a second process (CLI vs UI)
    on the same root.

    Exchanges are serialised by ``lock``; a child that dies or stops answering
    is restarted transparently.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[bytes] | None = None
        self.lines: queue.Queue[bytes | None] = queue.Queue()
        self.stderr: collections.deque[bytes] = collections.deque(maxlen=64)
        self.idle_since = time.monotonic()

    def call(self, line: bytes) -> bytes:
        """Send one request line and return its response line."""
        with self.lock:
            self._start()
            proc = self.proc
            try:
                proc.stdin.write(line)
                proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as exc:
                self._stop()
                raise _BridgeGone(str(exc)) from exc
            try:
                response = self.lines.get(timeout=REQUEST_TIMEOUT_S)
            except queue.Empty as exc:
                self._stop()
                raise _BridgeGone(f"no response within {REQUEST_TIMEOUT_S:.0f} s") from exc
            if response is None:
                self._stop()
                raise _BridgeGone(self._diagnostic())
            self.idle_since = time.monotonic()
            return response

    def close(self) -> None:
        with self.lock:
            self._stop()

    def retire_if_idle(self) -> None:
        """Stop the child after an idle spell; the next request starts a new one."""
        if time.monotonic() - self.idle_since < BRIDGE_IDLE_S:
            return
        if not self.lock.acquire(blocking=False):
            return
        try:
            if time.monotonic() - self.idle_since >= BRIDGE_IDLE_S:
                self._stop()
        finally:
            self.lock.release()

    def shutdown(self) -> None:
        """Kill the child at interpreter exit, without waiting for a request."""
        proc, self.proc = self.proc, None
        if proc is None:
            return
        if proc.poll() is None:
            with contextlib.suppress(OSError):
                proc.kill()
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            proc.wait(timeout=BRIDGE_GRACE_S)
        _close_pipes(proc)

    def _start(self) -> None:
        if self.proc is not None and self.proc.poll() is None:
            return
        self._stop()
        try:
            proc = subprocess.Popen(
                ["node", str(BRIDGE), str((self.root / "pouchdb").resolve())],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise RuntimeError(
                "PouchDB unavailable; install Node and npm ci in store/pouchdb"
            ) from exc
        self.lines = queue.Queue()
        self.stderr.clear()
        self.proc = proc
        self.idle_since = time.monotonic()
        for name, target, args in (
            ("filemaid-bridge-out", self._drain_stdout, (proc, self.lines)),
            ("filemaid-bridge-err", self._drain_stderr, (proc,)),
        ):
            threading.Thread(target=target, args=args, name=name, daemon=True).start()

    def _stop(self) -> None:
        proc, self.proc = self.proc, None
        if proc is None:
            return
        # Closing stdin lets the child finish its loop and exit on its own; a
        # bridge stuck on an operation is killed once the grace period is over.
        with contextlib.suppress(OSError, ValueError):
            if proc.stdin is not None:
                proc.stdin.close()
        try:
            proc.wait(timeout=BRIDGE_GRACE_S)
        except subprocess.TimeoutExpired:
            proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                proc.wait(timeout=BRIDGE_GRACE_S)
        _close_pipes(proc)

    def _drain_stdout(self, proc: subprocess.Popen, lines: queue.Queue) -> None:
        try:
            for line in proc.stdout:
                lines.put(line)
        except (OSError, ValueError):
            pass
        finally:
            lines.put(None)  # EOF: this generation of the child is done

    def _drain_stderr(self, proc: subprocess.Popen) -> None:
        tail = self.stderr
        try:
            for line in proc.stderr:
                tail.append(line)
        except (OSError, ValueError):
            pass

    def _diagnostic(self) -> str:
        detail = b"".join(self.stderr).decode(errors="replace").strip()
        return detail or "the bridge exited without a response"


_bridges: dict[Path, _Bridge] = {}
_bridges_lock = threading.Lock()
_reaper: threading.Thread | None = None


def _bridge_for(root: Path) -> _Bridge:
    """The resident bridge of a store root, started lazily on first use."""
    global _reaper
    key = root.resolve()
    with _bridges_lock:
        bridge = _bridges.get(key)
        if bridge is None:
            bridge = _Bridge(key)
            _bridges[key] = bridge
        if _reaper is None:
            _reaper = threading.Thread(
                target=_retire_idle, name="filemaid-bridge-reaper", daemon=True
            )
            _reaper.start()
        return bridge


def _retire_idle() -> None:
    while True:
        time.sleep(BRIDGE_IDLE_S / 2)
        for bridge in list(_bridges.values()):
            bridge.retire_if_idle()


@atexit.register
def _shutdown_bridges() -> None:
    for bridge in list(_bridges.values()):
        bridge.shutdown()


class PouchStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def request(self, **request: Any) -> Any:
        """One bridge operation, under the cross-process ``pouchdb.lock``.

        A bridge that died is restarted and the request replayed once: every
        operation is idempotent (an immutable put collides into a no-op, a local
        put compares and swaps), so an interrupted child cannot corrupt the
        store.
        """
        self.root.mkdir(parents=True, exist_ok=True)
        bridge = _bridge_for(self.root)
        line = canonical(request) + b"\n"
        for attempt in (0, 1):
            with interprocess_lock(self.root / "pouchdb.lock"):
                try:
                    response = json.loads(bridge.call(line))
                except _BridgeGone as exc:
                    if attempt:
                        raise RuntimeError(f"PouchDB bridge failed: {exc}") from exc
                    continue
                except ValueError as exc:
                    raise RuntimeError(f"PouchDB bridge failed: {exc}") from exc
            if not response.get("ok"):
                raise RuntimeError(f"PouchDB: {response.get('error', 'bridge failed')}")
            return response["result"]
        raise RuntimeError("PouchDB bridge failed: could not be restarted")

    def close(self) -> None:
        """Release the warm bridge of this root; later requests start a new one."""
        with _bridges_lock:
            bridge = _bridges.get(self.root.resolve())
        if bridge is not None:
            bridge.close()

    def batch(self, requests: list[dict]) -> list:
        """Run several operations in one round trip, in order.

        A failing operation aborts the batch and raises, like a failing single
        operation; the operations before it stay committed (no transaction).
        """
        if not requests:
            return []
        return self.request(op="batch", requests=list(requests))

    def put(self, doc: dict) -> str:
        self.request(op="put", doc=doc)
        return doc["_id"]

    def get(self, doc_id: str) -> dict | None:
        return self.request(op="get", id=doc_id)

    def list(self, prefix: str) -> list[dict]:
        return self.request(op="list", prefix=prefix)

    def for_file(self, file_id: str, kind: str | None = None) -> list[dict]:
        key = [file_id, kind] if kind else [file_id]
        return self.request(op="query", index="by_file", key=key)

    def artifact(self, identity: dict, stage: str, name: str, source: Any, media_type: str) -> str:
        import io
        import time
        import uuid

        stream = io.BytesIO(source) if isinstance(source, bytes) else source.open("rb")
        sha = hashlib.sha256()
        size = 0
        chunks = []
        with stream:
            while data := stream.read(CHUNK_SIZE):
                digest = hashlib.sha256(data).hexdigest()
                self.request(op="blob", sha256=digest, data=base64.b64encode(data).decode("ascii"))
                chunks.append(f"blob:{digest}")
                sha.update(data)
                size += len(data)
        doc_id = f"artifact:{identity['scan_id']}:{uuid.uuid4()}"
        self.put(
            {
                **identity,
                "_id": doc_id,
                "kind": "artifact",
                "stage": stage,
                "name": name,
                "media_type": media_type,
                "sha256": sha.hexdigest(),
                "size": size,
                "chunks": chunks,
                "timestamp": time.time(),
            }
        )
        return doc_id

    def read_artifact(self, doc_id: str):
        doc = self.get(doc_id)
        if doc is None or doc.get("kind") != "artifact":
            raise KeyError(doc_id)
        sha = hashlib.sha256()
        size = 0
        for chunk in doc["chunks"]:
            data = base64.b64decode(self.request(op="attachment", id=chunk), validate=True)
            _verify_chunk(chunk, data)
            sha.update(data)
            size += len(data)
            yield data
        if size != doc["size"] or sha.hexdigest() != doc["sha256"]:
            raise RuntimeError("PouchDB artifact checksum mismatch")

    def blobs(self, ids: list[str]) -> list[bytes]:
        """Several blob attachments in one round trip, in the given order."""
        if not ids:
            return []
        return [
            base64.b64decode(data, validate=True)
            for data in self.request(op="blobs", ids=list(ids))
        ]

    def hydrate(self, doc: dict) -> dict:
        return self.hydrate_many([doc])[0]

    def hydrate_many(self, docs: list[dict]) -> list[dict]:
        """Hydrate several documents; offloaded payloads cost two round trips.

        Documents without ``payload_ref`` are returned unchanged. Payload
        artifacts are read together (one batch for their documents, one for
        their chunks) and every chunk and total checksum is verified.
        """
        refs = list(dict.fromkeys(d["payload_ref"] for d in docs if "payload_ref" in d))
        if not refs:
            return list(docs)
        payloads = self._payloads(refs)
        return [{**d, **payloads[d["payload_ref"]]} if "payload_ref" in d else d for d in docs]

    def _payloads(self, refs: list[str]) -> dict[str, dict]:
        """The decoded JSON payload of several artifacts, keyed by artifact id."""
        plans: list[tuple[str, dict, int]] = []
        chunks: list[str] = []
        for ref, doc in zip(
            refs, self.batch([{"op": "get", "id": ref} for ref in refs]), strict=True
        ):
            if doc is None or doc.get("kind") != "artifact":
                raise KeyError(ref)
            plans.append((ref, doc, len(chunks)))
            chunks.extend(doc["chunks"])
        data = self.blobs(chunks)
        payloads = {}
        for ref, doc, start in plans:
            blobs = data[start : start + len(doc["chunks"])]
            _verify_artifact(doc, blobs)
            payloads[ref] = json.loads(b"".join(blobs))
        return payloads

    def local_get(self, name: str) -> dict | None:
        return self.request(op="local_get", id=name)

    def local_put(self, name: str, payload: dict) -> None:
        self.request(op="local_put", id=name, payload=payload)

    def selection(self) -> dict:
        """Withheld selection computed by the bridge from current documents."""
        return self.request(op="selection")

    def put_conditional(self, doc: dict, file_key: str, expected_decision_id: str) -> str:
        """Immutable put guarded by the file's current latest decision (atomic).

        The guard and the write happen inside one locked bridge operation, so a
        scan ingested concurrently cannot be resolved by accident.
        """
        self.request(
            op="put_conditional",
            doc=doc,
            file_key=file_key,
            expected_decision_id=expected_decision_id,
        )
        return doc["_id"]

    def sync(self, remote_url: str, token: str = "") -> dict:
        url = couchdb_url(remote_url)
        user = os.environ.get("FILEMAID_COUCHDB_USER", "")
        password = os.environ.get("FILEMAID_COUCHDB_PASSWORD", "")
        if bool(user) != bool(password):
            raise ValueError("Configure usuario y contraseña de CouchDB conjuntamente")
        if token and user:
            raise ValueError("Configure Basic o Bearer para CouchDB, no ambos")
        return self.request(
            op="sync", url=url, credentials={"user": user, "password": password, "token": token}
        )
