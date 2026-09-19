"""Configuración de la aplicación: rutas de estado en disco (nunca /tmp)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml


class AppConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.store_path = root / "store.db"
        self.ledger_path = root / "ledger.jsonl"
        self.cache_dir = root / "cache"
        self.pages_dir = root / "pages"
        self.master_dir = Path(os.environ.get("ALBERTITOS_MASTER", "master"))
        self.rules_config_path = Path(
            os.environ.get("ALBERTITOS_RULES", str(self.master_dir / "rules.yaml"))
        )
        self.extraction_config_path = Path(
            os.environ.get("ALBERTITOS_EXTRACTION", "master/extraction.yaml")
        )
        self.llama_base_url = os.environ.get("ALBERTITOS_LLAMA_URL", "http://127.0.0.1:8080/v1")
        self.cloud_api_key = os.environ.get("ALBERTITOS_CLOUD_API_KEY", "")

    @classmethod
    def load(cls) -> AppConfig:
        root = Path(os.environ.get("ALBERTITOS_DATA", "data"))
        return cls(root)

    def extraction_config(self) -> dict:
        raw = yaml.safe_load(self.extraction_config_path.read_bytes()) or {}
        return {
            "config_version": self.extraction_config_path.stem + ":"
            + hashlib.sha256(self.extraction_config_path.read_bytes()).hexdigest()[:12],
            "llama_base_url": self.llama_base_url,
            "cloud_api_key": self.cloud_api_key,
            "render_scale": 2.0,
            **raw,
        }
