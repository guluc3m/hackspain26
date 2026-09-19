"""Filemaid standalone VLM proxy server."""

from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import os
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from .llama_manager import get_manager
from .runtime import endpoint

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
    """Create FastAPI application hosting VLM proxy escalation."""
    token = (
        server_token if server_token is not None else os.environ.get("FILEMAID_SERVER_TOKEN", "")
    ).strip()

    upstream_vlm_url = endpoint(os.environ.get("FILEMAID_SERVER_VLM_URL", ""), "VLM upstream")
    upstream_vlm_key = os.environ.get("FILEMAID_SERVER_VLM_KEY", "").strip()

    vlm_semaphore = asyncio.Semaphore(MAX_CONCURRENT_VLM)
    app = FastAPI(title="Filemaid Server", version="0.1.0")

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
