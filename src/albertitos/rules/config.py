"""Configuración del motor de reglas: YAML → dataclass inmutable.

Las reglas y umbrales son DATOS (rules/regla_v3.yaml). Añadir una regla no
exige tocar la extracción; cambiar la v3 por la v4 es cambiar de yaml.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml


@dataclass(frozen=True)
class EngineConfig:
    rule_set: str
    version: str
    config_version: str
    rules: tuple[tuple[str, str], ...]  # (code, kind) en orden del yaml
    tolerancia_importe: float
    outlier_total: float
    ghost_iban: str
    estados_pagables: tuple[str, ...]
    anomaly_markers: tuple[str, ...]
    hojas_ignoradas: tuple[str, ...]
    fecha_referencia: str  # ISO YYYY-MM-DD; "fecha futura" se juzga contra esto
    extractor_versions: tuple[tuple[str, str], ...] = ()
    # T13: reglas definidas en el yaml pero DESACTIVADAS (pendientes de
    # especificación). Están en el snapshot; el motor no las evalúa.
    reglas_pendientes: tuple[str, ...] = ()
    # T13: umbrales paramétricos por regla (los pide la implementación).
    rule_params: tuple[tuple[str, dict], ...] = ()

    def params_for(self, code: str) -> dict:
        """Parámetros declarados en el yaml para una regla (datos, no código)."""
        return dict(dict(self.rule_params).get(code, {}))

    def snapshot(self) -> dict:
        """Snapshot determinista de la configuración activa (AGENTS.md §4)."""
        return {
            "rule_set": self.rule_set,
            "version": self.version,
            "config_version": self.config_version,
            "rules": {code: kind for code, kind in self.rules},
            "reglas_pendientes": list(self.reglas_pendientes),
            "rule_params": {code: dict(p) for code, p in self.rule_params},
            "tolerancia_importe": self.tolerancia_importe,
            "outlier_total": self.outlier_total,
            "estados_pagables": list(self.estados_pagables),
            "anomaly_markers": list(self.anomaly_markers),
            "hojas_ignoradas": list(self.hojas_ignoradas),
            "fecha_referencia": self.fecha_referencia,
            "extractor_versions": {k: v for k, v in self.extractor_versions},
        }


def load_config(path: str | pathlib.Path, *, fecha_referencia: str) -> EngineConfig:
    """Carga un set de reglas (p. ej. rules/regla_v3.yaml).

    `fecha_referencia` se pasa SIEMPRE explícita: el motor es puro y no lee
    el reloj del sistema (AGENTS.md §4).
    """
    from albertitos.rules.engine import RULES  # import perezoso: evita ciclo

    data = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))
    raw_rules = data["rules"]
    activas: list[tuple[str, str]] = []
    pendientes: list[str] = []
    for code, spec in raw_rules.items():
        code, activa, kind = str(code), True, None
        if isinstance(spec, dict):
            kind = spec.get("kind")
            activa = bool(spec.get("activa", True))
        else:
            kind = str(spec)
        if code not in RULES:
            raise ValueError(f"regla sin implementación en engine.RULES: {code}")
        if kind not in ("gate", "anomaly"):
            raise ValueError(f"clase de regla desconocida para {code}: {kind!r}")
        if activa:
            activas.append((code, str(kind)))
        else:
            pendientes.append(code)
    rules = tuple(activas)
    params = tuple(
        (str(code), dict(p or {}))
        for code, p in (data.get("rule_params") or {}).items()
    )
    return EngineConfig(
        rule_set=str(data["rule_set"]),
        version=str(data["version"]),
        config_version=str(data["config_version"]),
        rules=rules,
        reglas_pendientes=tuple(pendientes),
        rule_params=params,
        tolerancia_importe=float(data["tolerancia_importe"]),
        outlier_total=float(data["outlier_total"]),
        ghost_iban=str(data["ghost_iban"]),
        estados_pagables=tuple(str(e).upper() for e in data["estados_pagables"]),
        anomaly_markers=tuple(str(m).lower() for m in data["anomaly_markers"]),
        hojas_ignoradas=tuple(str(h) for h in data.get("hojas_ignoradas", ())),
        fecha_referencia=str(fecha_referencia),
        extractor_versions=tuple(
            (str(k), str(v)) for k, v in data.get("extractor_versions", {}).items()
        ),
    )


__all__ = ["EngineConfig", "load_config"]