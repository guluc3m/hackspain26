"""Filemaid standalone synchronization server and VLM proxy."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response

from .llama_manager import get_manager
from .runtime import endpoint
from .store.pouch import PouchStore

MAX_VLM_BODY_SIZE = 24 * 1024 * 1024
MAX_CONCURRENT_VLM = 4
MAX_BLOB_SIZE = 1024 * 1024  # 1 MiB limit matching PouchStore / bridge
MAX_JSON_BODY_SIZE = 2 * 1024 * 1024  # 2 MiB limit for JSON requests
VLM_TIMEOUT = 120.0

_SECRET_SCRUB_PATTERNS = [
    re.compile(r"(?:Bearer\s+)[A-Za-z0-9_\-\.]+"),
    re.compile(r"(?:key|token|auth|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]+['\"]?", re.IGNORECASE),
]


def _scrub_secrets(text: str) -> str:
    for pattern in _SECRET_SCRUB_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def _is_loopback_address(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_loopback
    except ValueError:
        return host in {"localhost", "127.0.0.1", "::1"}


async def _read_bounded_body(request: Request, max_size: int) -> bytes:
    """Read request body while streaming, enforcing max_size without allocating unbounded buffers."""
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=413, detail=f"Request body exceeds {max_size} bytes limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _forward_vlm(url: str, body: dict, key: str = "") -> Response:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with (
            httpx.AsyncClient(timeout=VLM_TIMEOUT, follow_redirects=False) as client,
            client.stream("POST", url, json=body, headers=headers) as response,
        ):
            if response.status_code >= 400:
                raise HTTPException(response.status_code, "VLM upstream rejected request")
            chunks = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > MAX_JSON_BODY_SIZE:
                    raise HTTPException(502, "VLM response exceeds size limit")
                chunks.append(chunk)
            return Response(b"".join(chunks), media_type="application/json")
    except httpx.HTTPError as exc:
        raise HTTPException(502, "VLM upstream unavailable") from exc


def create_server(cfg: Any, server_token: str | None = None) -> FastAPI:
    """Create FastAPI application hosting PouchDB synchronization and VLM escalation."""
    token = (
        server_token if server_token is not None else os.environ.get("FILEMAID_SERVER_TOKEN", "")
    ).strip()

    upstream_vlm_url = endpoint(os.environ.get("FILEMAID_SERVER_VLM_URL", ""), "VLM upstream")
    upstream_vlm_key = os.environ.get("FILEMAID_SERVER_VLM_KEY", "").strip()

    vlm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VLM)
    app = FastAPI(title="Filemaid Server", version="0.1.0")

    def _get_store() -> PouchStore:
        return PouchStore(cfg.root)

    @app.middleware("http")
    async def enforce_auth_and_fail_closed(request: Request, call_next):
        # Health check is public
        if request.url.path == "/healthz":
            return await call_next(request)

        # Check client address
        client_host = request.client.host if request.client else ""
        is_loopback = _is_loopback_address(client_host)

        # Non-loopback deployment MUST fail closed if server token is not configured
        if not is_loopback and not token:
            return JSONResponse(
                status_code=403,
                content={"error": "Server requires FILEMAID_SERVER_TOKEN for non-loopback access"},
            )

        # If a token is configured, enforce constant-time Bearer token authentication
        if token:
            auth_header = request.headers.get("Authorization", "")
            expected = f"Bearer {token}"
            if not auth_header or not hmac.compare_digest(auth_header.encode(), expected.encode()):
                return JSONResponse(
                    status_code=401,
                    content={"error": "Unauthorized: invalid or missing Bearer token"},
                )

        return await call_next(request)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/sync/info")
    def sync_info() -> dict[str, Any]:
        store = _get_store()
        try:
            return store.request(op="info")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=_scrub_secrets(str(exc))) from exc

    @app.post("/sync/push")
    async def sync_push(request: Request) -> dict[str, Any]:
        body_bytes = await _read_bounded_body(request, MAX_JSON_BODY_SIZE)

        try:
            payload = json.loads(body_bytes)
            docs = payload["docs"]
            if (
                not isinstance(docs, list)
                or not 1 <= len(docs) <= 32
                or any(not isinstance(d, dict) for d in docs)
            ):
                raise ValueError("invalid document list")
        except (ValueError, KeyError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from None

        def _do_push():
            store = _get_store()
            errors = []
            applied = []
            for doc in docs:
                doc_id = doc.get("_id", "")
                if not isinstance(doc_id, str) or not doc_id:
                    errors.append({"error": "missing_id"})
                    continue
                if doc_id.startswith("_"):
                    errors.append({"id": doc_id, "error": "reserved_id"})
                    continue
                if doc.get("_deleted"):
                    errors.append({"id": doc_id, "error": "immutable_tombstone_rejected"})
                    continue

                try:
                    res = store.request(op="sync_put", doc=doc)
                    applied.append(res)
                except RuntimeError as exc:
                    err_msg = str(exc)
                    if "collision" in err_msg.lower():
                        errors.append({"id": doc_id, "error": "collision"})
                    else:
                        errors.append({"id": doc_id, "error": _scrub_secrets(err_msg)})

            return {"ok": len(errors) == 0, "applied": applied, "errors": errors}

        return await asyncio.to_thread(_do_push)

    @app.get("/sync/pull")
    async def sync_pull(
        since: int = Query(0, ge=0),
        limit: int = Query(100, ge=1, le=500),
    ) -> dict[str, Any]:
        def _do_pull():
            store = _get_store()
            return store.request(op="changes", since=since, limit=limit)

        try:
            return await asyncio.to_thread(_do_pull)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=_scrub_secrets(str(exc))) from exc

    @app.get("/sync/document")
    def sync_document(id: str = Query(min_length=1, max_length=1024)) -> dict:
        if id.startswith("_"):
            raise HTTPException(403, "Reserved document")
        store = _get_store()
        doc = store.request(op="get_full", id=id)
        if doc is None:
            raise HTTPException(404, "Document not found")
        if id.startswith("blob:"):
            return {"_id": id, "kind": "blob"}
        if len(json.dumps(doc).encode()) > MAX_JSON_BODY_SIZE:
            raise HTTPException(413, "Document exceeds sync limit")
        return doc

    @app.get("/sync/blob/{sha256}")
    async def get_blob(sha256: str) -> Response:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise HTTPException(400, "Invalid blob hash")

        def _do_get():
            store = _get_store()
            doc_id = f"blob:{sha256}"
            try:
                data_b64 = store.request(op="attachment", id=doc_id)
            except Exception:
                return None
            return base64.b64decode(data_b64)

        data = await asyncio.to_thread(_do_get)
        if data is None:
            raise HTTPException(status_code=404, detail="Blob not found")

        return Response(content=data, media_type="application/octet-stream")

    @app.post("/sync/blob/{sha256}")
    async def put_blob(sha256: str, request: Request) -> dict[str, Any]:
        if not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise HTTPException(400, "Invalid blob hash")
        body = await _read_bounded_body(request, MAX_BLOB_SIZE)

        actual_sha = hashlib.sha256(body).hexdigest()
        if actual_sha != sha256:
            raise HTTPException(status_code=400, detail="SHA-256 checksum mismatch")

        def _do_put():
            store = _get_store()
            data_b64 = base64.b64encode(body).decode("ascii")
            store.request(op="blob", sha256=sha256, data=data_b64)

        try:
            await asyncio.to_thread(_do_put)
        except RuntimeError as exc:
            err_msg = str(exc)
            if "collision" in err_msg.lower():
                raise HTTPException(status_code=409, detail="Immutable blob collision") from exc
            raise HTTPException(status_code=500, detail=_scrub_secrets(err_msg)) from exc

        return {"ok": True, "sha256": sha256}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        body_bytes = await _read_bounded_body(request, MAX_VLM_BODY_SIZE)

        try:
            body = json.loads(body_bytes)
            if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
                raise TypeError("missing messages")
            if body.get("stream"):
                raise HTTPException(400, "Streaming is not supported by the escalator")
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None

        async with vlm_semaphore:
            if upstream_vlm_url:
                upstream_endpoint = (
                    f"{upstream_vlm_url}/chat/completions"
                    if upstream_vlm_url.endswith("/v1")
                    else f"{upstream_vlm_url}/v1/chat/completions"
                )
                return await _forward_vlm(upstream_endpoint, body, upstream_vlm_key)
            else:
                # Local llama-server manager fallback run via to_thread
                def _prepare_local_llama():
                    mgr = get_manager(cfg)
                    started = mgr.ensure_started()
                    if started:
                        mgr.touch()
                    return started, mgr.base_url

                started, base_url = await asyncio.to_thread(_prepare_local_llama)
                if not started:
                    raise HTTPException(status_code=503, detail="Local llama sidecar unavailable")

                local_endpoint = f"{base_url}/v1/chat/completions"
                return await _forward_vlm(local_endpoint, body)

    return app
