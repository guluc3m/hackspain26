"""Configuración de reglas: thresholds por campo/extractor, version y snapshot.

Los thresholds son configuración, no código. Cualquier cambio de política
NO_PAGAR/ESCALAR es una ADR (docs/decisiones/DECISIONS.md).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

from albertitos.types import Result

# Una regla rota jamás paga: solo puede resolver NO_PAGAR (negativo definitivo)
# o ESCALAR (duda razonable). PAGAR queda prohibido a propósito.
ON_FAIL_ALLOWED: tuple[str, ...] = (Result.NO_PAGAR.value, Result.ESCALAR.value)


class RuleConfig:
    def __init__(self, data: dict[str, Any], source_sha: str) -> None:
        self.data = data
        self.source_sha = source_sha
        self._validate_outcomes()

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
    def default_on_fail(self) -> str:
        outcomes = self.data.get("outcomes") or {}
        return str(outcomes.get("default", Result.NO_PAGAR.value)).upper()

    @property
    def on_fail_map(self) -> dict[str, str]:
        outcomes = self.data.get("outcomes") or {}
        raw = outcomes.get("on_fail") or {}
        return {str(code): str(value).upper() for code, value in raw.items()}

    def on_fail(self, rule_code: str) -> Result:
        """Resultado del motor cuando `rule_code` devuelve FAIL (configuración)."""
        return Result(self.on_fail_map.get(rule_code, self.default_on_fail))

    @property
    def outcomes(self) -> dict[str, Any]:
        """Sección de resultados tal cual, con el default resuelto."""
        return {"default": self.default_on_fail, "on_fail": self.on_fail_map}

    def _validate_outcomes(self) -> None:
        default = self.default_on_fail
        if default not in ON_FAIL_ALLOWED:
            raise ValueError(
                f"outcomes.default='{default}' no es válido; "
                f"una regla rota nunca paga: solo {list(ON_FAIL_ALLOWED)}"
            )
        for code, value in self.on_fail_map.items():
            if value not in ON_FAIL_ALLOWED:
                raise ValueError(
                    f"outcomes.on_fail.{code}='{value}' no es válido; "
                    f"una regla rota nunca paga: solo {list(ON_FAIL_ALLOWED)}"
                )

    @property
    def seleccion(self) -> dict[str, Any]:
        """Config de selección de valores (tests de formato, pesos, umbrales, ranking)."""
        return dict(self.data.get("seleccion", {}))

    @property
    def rule_outcomes(self) -> dict[str, str]:
        """Resultado resuelto (FAIL) por código de regla habilitada, para el snapshot."""
        codes = self.enabled_codes or list(self.on_fail_map)
        return {code: self.on_fail(code).value for code in codes}

    def snapshot(self, extractor_versions: dict[str, str], master_sha: str) -> dict[str, Any]:
        return {
            "config_version": self.version,
            "thresholds": self.thresholds,
            "extractor_versions": extractor_versions,
            "master_sha256": master_sha,
            "rule_outcomes": self.rule_outcomes,
        }

    @property
    def version(self) -> str:
        return self.source_sha
