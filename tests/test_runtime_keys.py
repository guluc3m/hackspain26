"""Claves de los últimos peldaños (Firecrawl, VLM cloud, TypeSafe System One).

Se guardan en el documento local de configuración (nunca replicado), valen en
ambos modos, entran enmascaradas por la API y jamás llegan a versiones,
evidencias ni trazas.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from filemaid.api.app import _vlm_status, create_app
from filemaid.config import AppConfig
from filemaid.extract.cache import FeatureCache
from filemaid.extract.rungs import typesafe_jev
from filemaid.extract.rungs.context import PageContext
from filemaid.pipeline import Pipeline
from filemaid.runtime import RuntimeSettings
from filemaid.store.pouch import PouchStore

# Claves de la configuración de extracción por campo del documento local.
CONFIG_FIELD = {
    "firecrawl_api_key": "firecrawl_api_key",
    "cloud_vlm_api_key": "cloud_api_key",
    "typesafe_api_key": "typesafe_api_key",
}
SECRETS = {
    "firecrawl_api_key": "fc-secret-0001",
    "cloud_vlm_api_key": "cloud-secret-0002",
    "typesafe_api_key": "ts-secret-0003",
}


def _config_keys(config: dict) -> dict:
    """Las tres claves tal y como las ve la escalera."""
    return {key: config[field] for key, field in CONFIG_FIELD.items()}


@pytest.fixture(autouse=True)
def _no_keys_in_env(monkeypatch):
    """Aísla cada test del entorno real: las claves solo vienen del documento local."""
    for name in ("FIRECRAWL_API_KEY", "FILEMAID_CLOUD_API_KEY", "TYPESAFE_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _make_text_pdf(path: Path, text: str) -> None:
    stream = f"BT /F1 10 Tf 50 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref_at = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    path.write_bytes(bytes(out))


def _evidence_blob(store: PouchStore) -> str:
    """Todo el espacio replicado (documentos, features, decisiones, adjuntos)."""
    return json.dumps(
        [store.hydrate(doc) for doc in store.list("")], ensure_ascii=False, default=str
    )


def test_keys_persist_and_survive_both_modes(cfg):
    settings = RuntimeSettings(cfg)
    settings.save({"mode": "standalone", **SECRETS})
    got = RuntimeSettings(cfg).get()
    assert {key: got[key] for key in SECRETS} == SECRETS
    # El resto del modo autónomo sigue limpiándose: las claves son la excepción.
    assert got["vlm_url"] == ""
    assert got["vlm_model"] == ""
    assert got["server_api_key"] == ""
    assert got["configured"] is True
    config = cfg.extraction_config()
    assert _config_keys(config) == SECRETS

    # En modo servidor tampoco se pierden.
    settings.save(
        {
            "mode": "server",
            "sync_url": "https://couch.example/facturas",
            "vlm_url": "https://vision.example/v1",
            "server_api_key": "srv-secret",
            **SECRETS,
        }
    )
    got = RuntimeSettings(cfg).get()
    assert {key: got[key] for key in SECRETS} == SECRETS
    # Y siguen siendo locales al dispositivo: nada entra en el espacio replicado.
    assert PouchStore(cfg.root).list("") == []


def test_extraction_config_prefers_saved_key_over_env(cfg, monkeypatch):
    monkeypatch.setenv("FIRECRAWL_API_KEY", "env-firecrawl")
    monkeypatch.setenv("FILEMAID_CLOUD_API_KEY", "env-cloud")
    monkeypatch.setenv("TYPESAFE_API_KEY", "env-typesafe")
    # AppConfig lee el entorno al construirse, como el resto de sus ajustes.
    env_cfg = AppConfig(cfg.root)
    RuntimeSettings(env_cfg).save({"mode": "standalone"})
    assert _config_keys(env_cfg.extraction_config()) == {
        "firecrawl_api_key": "env-firecrawl",
        "cloud_vlm_api_key": "env-cloud",
        "typesafe_api_key": "env-typesafe",
    }

    RuntimeSettings(env_cfg).save({"mode": "standalone", **SECRETS})
    config = env_cfg.extraction_config()
    # La clave guardada en el dispositivo gana sobre la variable de entorno.
    assert _config_keys(config) == SECRETS


def test_saved_key_enables_its_rung_in_standalone(cfg, tmp_path, monkeypatch):
    """El peldaño deja de saltarse por standalone cuando hay clave guardada."""
    gated = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=FeatureCache(tmp_path / "cache"),
        config=cfg.extraction_config(),
        page_image_sha="a" * 64,
        ocr_text="FACTURA 2026/001 TOTAL 121,00 EUR",
    )
    assert gated.config["remote_rungs_enabled"] is False
    assert typesafe_jev.extract(gated).extraction_method == "skipped:standalone-no-remote"

    RuntimeSettings(cfg).save({"mode": "standalone", "typesafe_api_key": "ts-secret"})
    config = cfg.extraction_config()
    assert config["remote_rungs_enabled"] is True

    calls: list[str] = []

    def post(url, **kwargs):
        calls.append(url)
        raise httpx.ConnectError("sin red en el test")

    monkeypatch.setattr(httpx, "post", post)
    enabled = PageContext(
        pdf_path=tmp_path / "doc.pdf",
        page_index=0,
        cache=FeatureCache(tmp_path / "cache2"),
        config=config,
        page_image_sha="b" * 64,
        ocr_text="FACTURA 2026/001 TOTAL 121,00 EUR",
    )
    feature = typesafe_jev.extract(enabled)
    # Llegó a la red (el gating no la cortó) y degradó por el fallo, no por el modo.
    assert calls == ["https://api.typesafe.ai/v1/systemone"]
    assert feature.extraction_method == "skipped:typesafe-error:ConnectError"


def test_config_version_hashes_presence_never_key_value(cfg):
    settings = RuntimeSettings(cfg)
    settings.save({"mode": "standalone", "firecrawl_api_key": "fc-secret-0001"})
    with_key = cfg.extraction_config()["config_version"]
    # Cambiar el valor no cambia la versión: no hay material secreto en el hash.
    settings.save({"mode": "standalone", "firecrawl_api_key": "otra-clave-distinta"})
    assert cfg.extraction_config()["config_version"] == with_key
    # Aparecer o desaparecer una clave sí: la caché se invalida por presencia.
    settings.save({"mode": "standalone"})
    without_key = cfg.extraction_config()["config_version"]
    assert without_key != with_key
    settings.save({"mode": "standalone", "cloud_vlm_api_key": "cloud-secret"})
    assert cfg.extraction_config()["config_version"] != without_key


def test_get_config_masks_keys_and_never_returns_them(cfg):
    client = TestClient(create_app(cfg))
    response = client.put("/api/config", json={"mode": "standalone", **SECRETS})
    assert response.status_code == 200
    for secret in SECRETS.values():
        assert secret not in response.text

    body = client.get("/api/config").json()
    for key, secret in SECRETS.items():
        assert body[key] == "****" + secret[-4:]
        assert body[f"{key}_set"] is True
    text = client.get("/api/config").text
    for secret in SECRETS.values():
        assert secret not in text


def test_put_keeps_on_empty_and_mask_replaces_and_clears(cfg):
    client = TestClient(create_app(cfg))
    client.put("/api/config", json={"mode": "standalone", **SECRETS})

    # Campo vacío (y campo ausente) conservan la clave guardada.
    assert client.put(
        "/api/config", json={"mode": "standalone", **{key: "" for key in SECRETS}}
    ).status_code == 200
    stored = RuntimeSettings(cfg).get()
    assert {key: stored[key] for key in SECRETS} == SECRETS

    # La máscara que devuelve GET conserva la clave guardada.
    mask = client.get("/api/config").json()
    assert client.put(
        "/api/config",
        json={
            "mode": "standalone",
            **{key: mask[key] for key in SECRETS},
        },
    ).status_code == 200
    stored = RuntimeSettings(cfg).get()
    assert {key: stored[key] for key in SECRETS} == SECRETS

    # Un valor nuevo reemplaza solo su clave.
    client.put("/api/config", json={"mode": "standalone", "firecrawl_api_key": "nueva-9999"})
    stored = RuntimeSettings(cfg).get()
    assert stored["firecrawl_api_key"] == "nueva-9999"
    assert stored["cloud_vlm_api_key"] == SECRETS["cloud_vlm_api_key"]
    assert stored["typesafe_api_key"] == SECRETS["typesafe_api_key"]

    # clear_keys borra las tres de golpe.
    assert client.put(
        "/api/config", json={"mode": "standalone", "clear_keys": True}
    ).status_code == 200
    stored = RuntimeSettings(cfg).get()
    assert {key: stored[key] for key in SECRETS} == {key: "" for key in SECRETS}
    assert client.get("/api/config").json()["firecrawl_api_key"] == ""


def test_config_never_reaches_evidence(cfg, tmp_path, monkeypatch):
    """Ninguna evidencia replicada contiene las claves (ni en claro ni derivadas)."""
    RuntimeSettings(cfg).save({"mode": "standalone", **SECRETS})

    def sin_red(*args, **kwargs):
        raise AssertionError("un peldaño remoto intentó salir a la red en el test")

    monkeypatch.setattr(httpx, "post", sin_red)
    cfg.root.mkdir(parents=True, exist_ok=True)
    lote = tmp_path / "lote"
    lote.mkdir(parents=True, exist_ok=True)
    _make_text_pdf(
        lote / "factura_ok.pdf",
        "FACTURA 2026/001 - Suministros Garcia SL - NIF B12345678 - IBAN ES91 2100 0418 4502 0005 1332"
        " - Pedido P-2026-001 - Fecha: 15/01/2026 - Base: 100,00 EUR - IVA 21% - Cuota IVA: 21,00 EUR - TOTAL : 121,00 EUR",
    )

    pipeline = Pipeline(cfg)
    decisions = pipeline.run_lote(lote, cfg.root / "outcomes.jsonl")
    assert len(decisions) == 1

    store = PouchStore(cfg.root)
    blob = _evidence_blob(store)
    for secret in SECRETS.values():
        assert secret not in blob
    # La clave vive donde debe: en el documento local (nunca replicado).
    assert store.local_get("runtime-settings")["firecrawl_api_key"] == SECRETS["firecrawl_api_key"]


class _StubProvisioner:
    """Provisioner de prueba: cuenta arranques y devuelve el estado pedido."""

    def __init__(self, probe: dict | None = None) -> None:
        self.starts = 0
        self._probe = probe or {
            "state": "idle",
            "in_flight": False,
            "downloaded": False,
            "running": False,
            "ready": False,
            "detail": "",
            "error": "",
        }

    def ensure(self, wait: bool = False) -> dict:
        self.starts += 1
        return self._probe

    def status(self) -> dict:
        return dict(self._probe)


def test_fresh_standalone_autostarts_local_vlm(cfg, monkeypatch):
    """Install nuevo (sin confirmar modo): el VLM local arranca solo por defecto."""
    stub = _StubProvisioner()
    monkeypatch.setattr("filemaid.api.app.get_provisioner", lambda cfg=None: stub)
    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/config").json()["vlm_autostart"] is True
        assert stub.starts == 1


def test_disabled_autostart_does_not_start_the_vlm(cfg, monkeypatch):
    RuntimeSettings(cfg).save({"mode": "standalone", "vlm_autostart": False})
    stub = _StubProvisioner()
    monkeypatch.setattr("filemaid.api.app.get_provisioner", lambda cfg=None: stub)
    with TestClient(create_app(cfg)) as client:
        assert client.get("/api/config").json()["vlm_autostart"] is False
    assert stub.starts == 0


def test_standalone_save_flips_only_the_checkbox(cfg):
    """Guardar el checkbox no exige re-confirmar el modo ni aportar URLs."""
    RuntimeSettings(cfg).save({"mode": "standalone", **SECRETS})
    client = TestClient(create_app(cfg))
    assert client.put("/api/config", json={"mode": "standalone", "vlm_autostart": False}).status_code == 200
    stored = RuntimeSettings(cfg).get()
    assert stored["vlm_autostart"] is False
    assert {key: stored[key] for key in SECRETS} == SECRETS
    assert client.get("/api/config").json()["vlm_autostart"] is False
    # Y se vuelve a activar con la misma facilidad.
    assert client.put("/api/config", json={"mode": "standalone", "vlm_autostart": True}).status_code == 200
    assert RuntimeSettings(cfg).get()["vlm_autostart"] is True


def test_vlm_status_never_busy_without_a_real_start(cfg, monkeypatch):
    RuntimeSettings(cfg).save({"mode": "standalone"})
    settings = RuntimeSettings(cfg)
    for probe_state in ("idle", "error", "ready"):
        probe = {"state": probe_state, "in_flight": False, "ready": probe_state == "ready"}
        monkeypatch.setattr("filemaid.api.app.get_provisioner", lambda cfg=None, p=probe: _StubProvisioner(p))
        reported = _vlm_status(cfg, settings)
        assert reported["state"] == probe_state
        assert reported["state"] not in {"downloading", "starting"}

    # Un "preparando" sin nada en marcha se degrada a la verdad observada.
    stale = {"state": "downloading", "in_flight": False, "ready": False}
    monkeypatch.setattr("filemaid.api.app.get_provisioner", lambda cfg=None: _StubProvisioner(stale))
    assert _vlm_status(cfg, settings)["state"] == "idle"
    stale["ready"] = True
    assert _vlm_status(cfg, settings)["state"] == "ready"
    # Un arranque real sí se informa como tal.
    real = {"state": "starting", "in_flight": True, "ready": False}
    monkeypatch.setattr("filemaid.api.app.get_provisioner", lambda cfg=None: _StubProvisioner(real))
    assert _vlm_status(cfg, settings)["state"] == "starting"
