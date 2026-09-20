from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from filemaid.config import AppConfig
from filemaid.provision import MODEL_FILES
from filemaid.rules.config import RuleConfig
from filemaid.rules.master import MasterData, Pedido, Proveedor
from filemaid.store.pouch import PouchStore

REPO_ROOT = Path(__file__).resolve().parent.parent


class FakeProvisioner:
    """Dependency stub: tests never download or start a real VLM."""

    def __init__(self, ready: bool = False) -> None:
        self._ready = ready

    def ensure(self, wait: bool = False) -> dict:
        return self.status()

    def status(self) -> dict:
        total = sum(size for _name, size, _sha in MODEL_FILES)
        return {
            "state": "ready" if self._ready else "idle",
            "downloaded": self._ready,
            "running": self._ready,
            "ready": self._ready,
            "detail": "",
            "error": "",
            "progress": 1.0 if self._ready else None,
            "bytes_done": total if self._ready else 0,
            "bytes_total": total,
            "file": None,
            "model": "",
            "mmproj": "",
            "binary": None,
        }


@pytest.fixture(autouse=True)
def _fake_provisioner(monkeypatch):
    """Inject a not-ready provisioner by default; readiness tests inject their own."""
    fake = FakeProvisioner()
    monkeypatch.setattr("filemaid.provision.get_provisioner", lambda cfg=None: fake)
    monkeypatch.setattr("filemaid.api.app.get_provisioner", lambda cfg=None: fake)
    monkeypatch.setattr("filemaid.server.get_provisioner", lambda cfg=None: fake)


@pytest.fixture
def cfg(tmp_path: Path) -> AppConfig:
    cfg = AppConfig(tmp_path / "data")
    cfg.master_dir = tmp_path / "master"
    cfg.master_dir.mkdir(parents=True, exist_ok=True)
    for name in ("rules.yaml", "proveedores.csv", "pedidos.csv"):
        shutil.copy(REPO_ROOT / "master" / name, cfg.master_dir / name)
    cfg.rules_config_path = cfg.master_dir / "rules.yaml"
    return cfg


@pytest.fixture
def store(cfg: AppConfig) -> PouchStore:
    return PouchStore(cfg.root)


@pytest.fixture
def master() -> MasterData:
    m = MasterData()
    m.proveedores["B12345678"] = Proveedor("B12345678", "Suministros García SL", "ES9121000418450200051332")
    m.pedidos["P-2026-001"] = Pedido("P-2026-001", "B12345678", 121.00, "PENDIENTE", False)
    return m


@pytest.fixture
def rule_config(cfg: AppConfig) -> RuleConfig:
    return RuleConfig.load(REPO_ROOT / "master" / "rules.yaml")
