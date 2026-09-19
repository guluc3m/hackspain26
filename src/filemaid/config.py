"""Configuración de la aplicación: rutas de estado en disco (nunca /tmp)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import yaml


class AppConfig:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.pages_dir = root / "pages"
        self.master_dir = Path(os.environ.get("FILEMAID_MASTER", "master"))
        self.rules_config_path = Path(
            os.environ.get("FILEMAID_RULES", str(self.master_dir / "rules.yaml"))
        )
        self.extraction_config_path = Path(
            os.environ.get("FILEMAID_EXTRACTION", "master/extraction.yaml")
        )
        self.llama_base_url = os.environ.get("FILEMAID_LLAMA_URL", "http://127.0.0.1:8080/v1")
        self.cloud_api_key = os.environ.get("FILEMAID_CLOUD_API_KEY", "")
        self.typesafe_api_url = os.environ.get(
            "TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone"
        )
        self.typesafe_api_key = os.environ.get("TYPESAFE_API_KEY", "")
        self.typesafe_model = os.environ.get("TYPESAFE_MODEL", "jev-latest")
        self.firecrawl_api_url = os.environ.get(
            "FIRECRAWL_API_URL", "https://api.firecrawl.dev/v2/parse"
        )
        self.firecrawl_api_key = os.environ.get("FIRECRAWL_API_KEY", "")

    @classmethod
    def load(cls) -> AppConfig:
        root = Path(os.environ.get("FILEMAID_DATA", "data"))
        return cls(root)

    def runtime_settings(self) -> dict:
        from .runtime import RuntimeSettings

        return RuntimeSettings(self).get()

    def extraction_config(self) -> dict:
        raw = yaml.safe_load(self.extraction_config_path.read_bytes()) or {}
        settings = self.runtime_settings()
        mode = settings["mode"]
        fallback = settings["local_vlm_fallback"]
        standalone = mode == "standalone"
        # Standalone always uses the local sidecar and never contacts a remote
        # VLM, even if a stale endpoint was saved or exported in the env.
        vlm_url = "" if standalone else settings["vlm_url"]
        # Ephemeral secret consumed only by the remote VLM rung. It is never part
        # of the config_version hash, the decision snapshot, evidence or logs.
        vlm_api_key = "" if standalone else settings["server_api_key"]
        config = {
            "config_version": self.extraction_config_path.stem
            + ":"
            + hashlib.sha256(
                self.extraction_config_path.read_bytes()
                + repr((mode, fallback, vlm_url, settings["vlm_model"])).encode()
            ).hexdigest()[:12],
            "llama_base_url": self.llama_base_url,
            "cloud_api_key": self.cloud_api_key,
            "typesafe_api_url": self.typesafe_api_url,
            "typesafe_api_key": self.typesafe_api_key,
            "typesafe_model": self.typesafe_model,
            "firecrawl_api_url": self.firecrawl_api_url,
            "firecrawl_api_key": self.firecrawl_api_key,
            "render_scale": 2.0,
            **raw,
        }
        config["mode"] = mode
        config["local_vlm_fallback"] = fallback
        config["remote_rungs_enabled"] = not standalone
        config["vlm_base_url"] = vlm_url
        config["vlm_model"] = settings["vlm_model"]
        config["vlm_api_key"] = vlm_api_key
        return config
