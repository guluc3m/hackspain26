"""Filemaid VLM server: hosts the local PaddleOCR-VL Q8 sidecar.

The server is always local: startup provisions (install + start + health-check)
the local llama.cpp sidecar and refuses to serve if it is not ready. There is no
remote-upstream mode; the client's optional local fallback is a separate concern.
"""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import os
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .llama_manager import get_manager
from .provision import get_provisioner

MAX_VLM_BODY_SIZE = 24 * 1024 * 1024
MAX_CONCURRENT_VLM = 4
MAX_JSON_BODY_SIZE = 2 * 1024 * 1024  # 2 MiB limit for JSON requests
VLM_TIMEOUT = 120.0


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


async def _forward_vlm(url: str, body: dict) -> Response:
    try:
        async with (
            httpx.AsyncClient(timeout=VLM_TIMEOUT, follow_redirects=False) as client,
            client.stream("POST", url, json=body) as response,
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


def create_server(cfg: Any, server_token: str | None = None, provisioner: Any = None) -> FastAPI:
    """Create the FastAPI app hosting the local VLM sidecar (mandatory at startup)."""
    token = (
        server_token if server_token is not None else os.environ.get("FILEMAID_SERVER_TOKEN", "")
    ).strip()
    provisioner = provisioner or get_provisioner(cfg)

    vlm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VLM)

    @asynccontextmanager
    async def lifespan(_app):
        status = await asyncio.to_thread(provisioner.ensure, True)
        if not status.get("ready"):
            raise RuntimeError(
                f"VLM local no disponible: {status.get('error') or status.get('detail') or 'no listo'}"
            )
        yield

    app = FastAPI(title="Filemaid Server", version="0.1.0", lifespan=lifespan)

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
    async def healthz() -> dict[str, Any]:
        # Live probe (no model spin-up): reflects a stopped/crashed sidecar.
        status = await asyncio.to_thread(provisioner.status)
        return {"status": "ok", "vlm_ready": bool(status.get("ready"))}

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
            # Forward to the healthy local sidecar (mandatory local VLM).
            def _prepare_local_llama():
                mgr = get_manager(cfg)
                started = mgr.ensure_started()
                if started:
                    mgr.touch()
                return started, mgr.base_url

            started, base_url = await asyncio.to_thread(_prepare_local_llama)
            if not started:
                raise HTTPException(status_code=503, detail="Local llama sidecar unavailable")
            return await _forward_vlm(f"{base_url}/v1/chat/completions", body)

    return app
