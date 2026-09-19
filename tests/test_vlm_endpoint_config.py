from __future__ import annotations

import httpx

from filemaid.extract.cache import FeatureCache
from filemaid.extract.rungs import vlm_local
from filemaid.extract.rungs.context import PageContext


def test_custom_endpoint_never_receives_sync_credential(tmp_path, monkeypatch):
    monkeypatch.setenv("FILEMAID_SYNC_TOKEN", "sync-secret-not-for-provider")
    monkeypatch.setenv("FILEMAID_VLM_KEY", "provider-secret")
    image = tmp_path / "p0.png"
    image.write_bytes(b"png")
    requests = []

    def post(url, **kwargs):
        requests.append((url, kwargs))
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
    ctx = PageContext(
        pdf_path=tmp_path / "invoice.pdf",
        page_index=0,
        cache=FeatureCache(tmp_path / "state"),
        pages_dir=tmp_path,
        page_image_sha="page",
        config={
            "config_version": "custom",
            "vlm_base_url": "https://provider.invalid/v1",
            "vlm_model": "configured-model",
            "rungs": {"vlm_local": {"min_field_coverage": 0}},
        },
    )
    feature = vlm_local.extract(ctx)
    assert feature.data.startswith("FACTURA")
    assert requests[0][0] == "https://provider.invalid/v1/chat/completions"
    assert requests[0][1]["headers"]["Authorization"] == "Bearer provider-secret"
    assert requests[0][1]["json"]["model"] == "configured-model"
    assert "sync-secret" not in str(requests)


def test_config_key_is_used_for_remote_vlm(tmp_path, monkeypatch):
    monkeypatch.delenv("FILEMAID_VLM_KEY", raising=False)
    monkeypatch.setenv("FILEMAID_SYNC_TOKEN", "sync-secret-not-for-provider")
    image = tmp_path / "p0.png"
    image.write_bytes(b"png")
    requests = []

    def post(url, **kwargs):
        requests.append((url, kwargs))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "FACTURA NIF B12345678 TOTAL 121,00 EUR"}}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "post", post)
    ctx = PageContext(
        pdf_path=tmp_path / "invoice.pdf",
        page_index=0,
        cache=FeatureCache(tmp_path / "state"),
        pages_dir=tmp_path,
        page_image_sha="page",
        config={
            "config_version": "custom",
            "vlm_base_url": "https://provider.invalid/v1",
            "vlm_model": "configured-model",
            "vlm_api_key": "config-secret",
            "rungs": {"vlm_local": {"min_field_coverage": 0}},
        },
    )
    feature = vlm_local.extract(ctx)
    assert feature.data.startswith("FACTURA")
    assert requests[0][1]["headers"]["Authorization"] == "Bearer config-secret"
    assert "sync-secret" not in str(requests)
