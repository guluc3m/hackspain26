"""Append-only PouchDB exchange over the filemaid HTTP service, not CouchDB."""
from __future__ import annotations

import base64
import fcntl
import hashlib
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx

from .pouch import CHUNK_SIZE, canonical

if TYPE_CHECKING:
    from .pouch import PouchStore

PAGE_LIMIT = 32
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024


def clean_document(doc: dict) -> dict:
    if doc.get("_conflicts") or doc.get("_deleted"):
        raise RuntimeError("Conflicted or deleted document cannot be synchronized")
    clean = {k: v for k, v in doc.items() if k not in {"_rev", "_conflicts"}}
    if "_attachments" in clean:
        clean["_attachments"] = {
            name: {"content_type": attachment["content_type"], "data": attachment["data"]}
            for name, attachment in clean["_attachments"].items()
        }
    return clean


def dependencies(doc: dict) -> list[str]:
    refs = []
    if isinstance(doc.get("payload_ref"), str):
        refs.append(doc["payload_ref"])
    if doc.get("kind") == "artifact":
        refs.extend(doc.get("chunks", []))
    return list(dict.fromkeys(refs))


def _response(client: httpx.Client, method: str, url: str, *, max_bytes=MAX_DOCUMENT_BYTES, **kwargs) -> bytes:
    with client.stream(method, url, **kwargs) as response:
        if response.status_code >= 400:
            # Remote error bodies may echo credentials; never surface them.
            raise RuntimeError(f"Synchronization HTTP {response.status_code}")
        chunks = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > max_bytes:
                raise RuntimeError("Synchronization response exceeds size limit")
            chunks.append(chunk)
        return b"".join(chunks)


def sync_store(store: PouchStore, remote_url: str, token: str = "") -> dict:
    import json

    url = urlsplit(remote_url)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password or url.query or url.fragment:
        raise ValueError("Sync endpoint must be an HTTP(S) URL without credentials")
    base = remote_url.rstrip("/") + "/"
    store.root.mkdir(parents=True, exist_ok=True)
    # Serializes entire checkpoint exchange across app/background/CLI processes.
    with (store.root / "sync.lock").open("a+b") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        with httpx.Client(base_url=base, headers=headers, timeout=60, follow_redirects=False) as client:
            def remote_json(method, path, **kwargs):
                return json.loads(_response(client, method, path, **kwargs))

            remote = remote_json("GET", "sync/info")
            remote_id = remote.get("instance_id")
            if not isinstance(remote_id, str) or not remote_id:
                raise RuntimeError("Remote database identity missing")
            local_id = store.request(op="info")["instance_id"]
            checkpoint_id = "sync-" + hashlib.sha256(base.encode()).hexdigest()
            checkpoint = store.local_get(checkpoint_id) or {}
            if checkpoint.get("remote_id") != remote_id or checkpoint.get("local_id") != local_id:
                checkpoint = {"remote_id": remote_id, "local_id": local_id, "push": 0, "pull": 0}
            counts = {"pushed": 0, "pulled": 0}
            pushed, pulled = set(), set()

            def push(doc_id: str, visiting: set):
                if doc_id in pushed:
                    return
                if doc_id.startswith("_") or doc_id in visiting:
                    raise RuntimeError("Reserved or cyclic synchronization dependency")
                doc = store.request(op="get_full", id=doc_id)
                if doc is None:
                    raise RuntimeError(f"Missing dependency: {doc_id}")
                visiting.add(doc_id)
                for dep in dependencies(doc):
                    push(dep, visiting)
                if doc_id.startswith("blob:"):
                    data = base64.b64decode(store.request(op="attachment", id=doc_id), validate=True)
                    _response(client, "POST", "sync/blob/" + doc_id[5:], content=data)
                else:
                    clean = clean_document(doc)
                    payload = canonical({"docs": [clean]})
                    if len(payload) > MAX_DOCUMENT_BYTES:
                        raise RuntimeError("Document exceeds sync limit; store large payloads as artifacts")
                    reply = remote_json("POST", "sync/push", content=payload, headers={"Content-Type": "application/json"})
                    if not reply.get("ok") or reply.get("errors"):
                        raise RuntimeError("Immutable synchronization collision or rejected document")
                visiting.remove(doc_id)
                pushed.add(doc_id)
                counts["pushed"] += 1

            def pull(doc: dict, visiting: set):
                doc_id = doc.get("_id")
                if not isinstance(doc_id, str) or doc_id.startswith("_") or doc_id in visiting:
                    raise RuntimeError("Reserved or cyclic synchronization document")
                if doc_id in pulled:
                    return
                visiting.add(doc_id)
                for dep in dependencies(doc):
                    if dep not in pulled:
                        dep_doc = remote_json("GET", "sync/document", params={"id": dep})
                        pull(dep_doc, visiting)
                if doc_id.startswith("blob:"):
                    data = _response(client, "GET", "sync/blob/" + doc_id[5:], max_bytes=CHUNK_SIZE)
                    store.request(op="blob", sha256=doc_id[5:], data=base64.b64encode(data).decode())
                else:
                    store.request(op="sync_put", doc=clean_document(doc))
                visiting.remove(doc_id)
                pulled.add(doc_id)
                counts["pulled"] += 1

            for direction in ("push", "pull"):
                while True:
                    since = checkpoint[direction]
                    if direction == "push":
                        page = store.request(op="changes", since=since, limit=PAGE_LIMIT)
                    else:
                        page = remote_json("GET", "sync/pull", params={"since": since, "limit": PAGE_LIMIT})
                    last = page.get("last_seq")
                    if not isinstance(last, int) or last < since:
                        raise RuntimeError("Invalid synchronization sequence")
                    for doc in page["results"]:
                        if direction == "push":
                            push(doc["_id"], set())
                        else:
                            pull(doc, set())
                    checkpoint[direction] = last
                    store.local_put(checkpoint_id, checkpoint)
                    if last == since:
                        break
            return {"ok": True, **counts, "local_seq": checkpoint["push"], "remote_seq": checkpoint["pull"]}
