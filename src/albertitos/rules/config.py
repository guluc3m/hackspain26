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

    def snapshot(self) -> dict:
        """Snapshot determinista de la configuración activa (AGENTS.md §4)."""
        return {
            "rule_set": self.rule_set,
            "version": self.version,
            "config_version": self.config_version,
            "rules": {code: kind for code, kind in self.rules},
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
    rules = tuple((str(code), str(kind)) for code, kind in data["rules"].items())
    desconocidas = [code for code, _ in rules if code not in RULES]
    if desconocidas:
        raise ValueError(f"reglas sin implementación en engine.RULES: {desconocidas}")
    return EngineConfig(
        rule_set=str(data["rule_set"]),
        version=str(data["version"]),
        config_version=str(data["config_version"]),
        rules=rules,
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