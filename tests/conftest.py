from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from filemaid.config import AppConfig
from filemaid.rules.config import RuleConfig
from filemaid.rules.master import MasterData, Pedido, Proveedor
from filemaid.store.db import Store

REPO_ROOT = Path(__file__).resolve().parent.parent


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
def store(cfg: AppConfig) -> Store:
    return Store(cfg.store_path)


@pytest.fixture
def master() -> MasterData:
    m = MasterData()
    m.proveedores["B12345678"] = Proveedor("B12345678", "Suministros García SL", "ES9121000418450200051332")
    m.pedidos["P-2026-001"] = Pedido("P-2026-001", "B12345678", 121.00, "PENDIENTE", False)
    return m


@pytest.fixture
def rule_config(cfg: AppConfig) -> RuleConfig:
    return RuleConfig.load(REPO_ROOT / "master" / "rules.yaml")
