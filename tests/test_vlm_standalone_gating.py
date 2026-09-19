"""Standalone remote gating and server-mode local VLM fallback."""

from __future__ import annotations

import httpx

from filemaid.extract.cache import FeatureCache
from filemaid.extract.rungs import cloud_vlm, firecrawl, typesafe_jev, vlm_local
from filemaid.extract.rungs.context import PageContext


def _ctx(tmp_path, **config) -> PageContext:
    (tmp_path / "p0.png").write_bytes(b"png")
    return PageContext(
        pdf_path=tmp_path / "invoice.pdf",
        page_index=0,
        cache=FeatureCache(tmp_path / "state"),
        pages_dir=tmp_path,
        page_image_sha="page",
        config={"config_version": "v", **config},
    )


def test_standalone_skips_remote_rungs_without_network(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("remote rung attempted network in standalone")

    monkeypatch.setattr(httpx, "post", boom)
    ctx = _ctx(tmp_path, remote_rungs_enabled=False)
    assert typesafe_jev.extract(ctx).extraction_method == "skipped:standalone-no-remote"
    assert firecrawl.extract(ctx).extraction_method == "skipped:standalone-no-remote"
    assert cloud_vlm.extract(ctx).extraction_method == "skipped:standalone-no-remote"


def test_local_fallback_used_when_remote_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_VLM_KEY", "remote-secret")
    calls: list[tuple[str, dict]] = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if "remote.invalid" in url:
            raise httpx.ConnectError("remote down")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "FACTURA NIF B12345678 TOTAL 121,00 EUR Fecha 15/01/2026"
                        }
                    }
                ]
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(
        vlm_local, "_local_endpoint", lambda: "http://127.0.0.1:8080/v1/chat/completions"
    )
    ctx = _ctx(
        tmp_path,
        vlm_base_url="https://remote.invalid/v1",
        vlm_model="remote-model",
        local_vlm_fallback=True,
        rungs={"vlm_local": {"min_field_coverage": 0}},
    )
    feature = vlm_local.extract(ctx)
    assert feature.data.startswith("FACTURA")
    # The remote call carries the remote auth + model; the local fallback carries neither.
    assert calls[0][0] == "https://remote.invalid/v1/chat/completions"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer remote-secret"
    assert calls[0][1]["json"]["model"] == "remote-model"
    assert calls[1][0] == "http://127.0.0.1:8080/v1/chat/completions"
    assert "Authorization" not in calls[1][1].get("headers", {})
    assert "model" not in calls[1][1]["json"]


def test_non_json_200_degrades_not_aborts(tmp_path, monkeypatch):
    # A 200 with a non-JSON body (proxy/captive portal) must degrade, not raise.
    def post(url, **kwargs):
        return httpx.Response(
            200,
            content=b"<html>captive portal</html>",
            headers={"content-type": "text/html"},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(
        vlm_local, "_local_endpoint", lambda: "http://127.0.0.1:8080/v1/chat/completions"
    )
    ctx = _ctx(tmp_path, rungs={"vlm_local": {"min_field_coverage": 0}})
    assert vlm_local.extract(ctx).extraction_method == "skipped:vlm-error"


def test_no_local_fallback_when_disabled(tmp_path, monkeypatch):
    def post(url, **kwargs):
        raise httpx.ConnectError("remote down")

    def forbidden_local():
        raise AssertionError("local VLM must not be contacted when fallback is disabled")

    monkeypatch.setattr(httpx, "post", post)
    monkeypatch.setattr(vlm_local, "_local_endpoint", forbidden_local)
    ctx = _ctx(
        tmp_path,
        vlm_base_url="https://remote.invalid/v1",
        local_vlm_fallback=False,
        rungs={"vlm_local": {"min_field_coverage": 0}},
    )
    assert vlm_local.extract(ctx).extraction_method == "skipped:vlm-error"
