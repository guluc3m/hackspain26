"""Configuración de la aplicación: rutas de estado en disco (nunca /tmp)."""

from __future__ import annotations

import os
from pathlib import Path


class AppConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.store_path = root / "store.db"
        self.ledger_path = root / "ledger.jsonl"
        self.cache_dir = root / "cache"
        self.pages_dir = root / "pages"
        self.master_dir = Path(os.environ.get("ALBERTITOS_MASTER", "master"))
        self.rules_config_path = Path(os.environ.get("ALBERTITOS_RULES", "master/rules.yaml"))
        self.llama_base_url = os.environ.get("ALBERTITOS_LLAMA_URL", "http://127.0.0.1:8080/v1")
        self.cloud_api_key = os.environ.get("ALBERTITOS_CLOUD_API_KEY", "")

    @classmethod
    def load(cls) -> AppConfig:
        root = Path(os.environ.get("ALBERTITOS_DATA", "data"))
        return cls(root)

    def extraction_config(self) -> dict:
        return {
            "config_version": self.rules_config_path.stem,
            "llama_base_url": self.llama_base_url,
            "cloud_api_key": self.cloud_api_key,
            "render_scale": 2.0,
        }
