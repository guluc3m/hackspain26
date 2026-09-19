"""Configuración de reglas: thresholds por campo/extractor, version y snapshot.

Los thresholds son configuración, no código. Cualquier cambio de política
NO_PAGAR/ESCALAR es una ADR (docs/decisiones/DECISIONS.md).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml


class RuleConfig:
    def __init__(self, data: dict[str, Any], source_sha: str) -> None:
        self.data = data
        self.source_sha = source_sha

    @classmethod
    def load(cls, path: Path) -> RuleConfig:
        raw = path.read_bytes()
        data = yaml.safe_load(raw) or {}
        return cls(data, hashlib.sha256(raw).hexdigest()[:12])

    @property
    def enabled_codes(self) -> list[str]:
        return [str(c) for c in self.data.get("rules", {}).get("enabled", [])]

    @property
    def thresholds(self) -> dict[str, Any]:
        return dict(self.data.get("thresholds", {}))

    @property
    def seleccion(self) -> dict[str, Any]:
        """Config de selección de valores (tests de formato, pesos, umbrales, ranking)."""
        return dict(self.data.get("seleccion", {}))

    def snapshot(self, extractor_versions: dict[str, str], master_sha: str) -> dict[str, Any]:
        return {
            "config_version": self.version,
            "thresholds": self.thresholds,
            "extractor_versions": extractor_versions,
            "master_sha256": master_sha,
        }

    @property
    def version(self) -> str:
        return self.source_sha
