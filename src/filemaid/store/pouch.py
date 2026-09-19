"""Local JS PouchDB, with serialized finite Node operations (no server)."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

CHUNK_SIZE = 1024 * 1024
INLINE_LIMIT = 256 * 1024
BRIDGE = Path(__file__).with_name("pouchdb") / "bridge.mjs"


def canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode("utf-8")


def file_key(file_id: str, sha256: str) -> str:
    return hashlib.sha256(canonical([file_id, sha256])).hexdigest()


class PouchStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def request(self, **request: Any) -> Any:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "pouchdb.lock").open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                proc = subprocess.run(
                    ["node", str(BRIDGE), str((self.root / "pouchdb").resolve())],
                    input=canonical(request),
                    capture_output=True,
                    timeout=120,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise RuntimeError(
                    "PouchDB unavailable; install Node and npm ci in store/pouchdb"
                ) from exc
            try:
                response = json.loads(proc.stdout)
            except ValueError as exc:
                raise RuntimeError(
                    f"PouchDB bridge failed: {proc.stderr.decode(errors='replace')}"
                ) from exc
            if proc.returncode or not response.get("ok"):
                raise RuntimeError(f"PouchDB: {response.get('error', 'bridge failed')}")
            return response["result"]

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
            if hashlib.sha256(data).hexdigest() != chunk.removeprefix("blob:"):
                raise RuntimeError("PouchDB attachment checksum mismatch")
            sha.update(data)
            size += len(data)
            yield data
        if size != doc["size"] or sha.hexdigest() != doc["sha256"]:
            raise RuntimeError("PouchDB artifact checksum mismatch")

    def hydrate(self, doc: dict) -> dict:
        if "payload_ref" not in doc:
            return doc
        payload = json.loads(b"".join(self.read_artifact(doc["payload_ref"])))
        return {**doc, **payload}

    def local_get(self, name: str) -> dict | None:
        return self.request(op="local_get", id=name)

    def local_put(self, name: str, payload: dict) -> None:
        self.request(op="local_put", id=name, payload=payload)

    def sync(self, remote_url: str, token: str = "") -> dict:
        from .sync import sync_store

        return sync_store(self, remote_url, token)
