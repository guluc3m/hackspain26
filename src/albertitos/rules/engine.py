"""Motor de decisión: determinista y puro. Sin I/O, sin reloj, sin azar.

Mismos campos + misma config + mismo maestro ⇒ misma salida, byte a byte.
Política de agregación (docs/normas.md + AGENTS.md §6):
  - cualquier FAIL  ⇒ NO_PAGAR (negativo definitivo, inmune a juicio humano)
  - si no, UNKNOWN  ⇒ ESCALAR (duda razonable: escalar antes que pagar)
  - si no, todo PASS⇒ PAGAR
"""

from __future__ import annotations

from albertitos.types import ConfigSnapshot, Decision, ExtractionField, Result, RuleVerdict

from .base import MasterData, RuleContext
from .config import RuleConfig
from .rules import all_rules


def evaluate(
    fields: dict[str, ExtractionField],
    master: MasterData,
    rule_config: RuleConfig,
    invoice_id: str,
    file_id: str,
    extractor_versions: dict[str, str] | None = None,
) -> Decision:
    ctx = RuleContext(fields=fields, master=master, thresholds=rule_config.thresholds)
    enabled = set(rule_config.enabled_codes) or {r.code for r in all_rules()}

    evaluations = [
        rule.evaluate(ctx)
        for rule in sorted((r for r in all_rules() if r.code in enabled), key=lambda r: r.code)
    ]

    verdicts = [e.verdict for e in evaluations]
    if RuleVerdict.FAIL in verdicts:
        result = Result.NO_PAGAR
    elif RuleVerdict.UNKNOWN in verdicts or not evaluations:
        result = Result.ESCALAR
    else:
        result = Result.PAGAR

    snapshot = ConfigSnapshot(
        rule_set_version=rule_config.rule_set_version,
        thresholds=rule_config.thresholds,
        extractor_versions=extractor_versions or {},
        master_sha256=master.sha256,
        config_version=rule_config.version,
    )
    return Decision(
        invoice_id=invoice_id,
        file_id=file_id,
        result=result,
        rule_evaluations=evaluations,
        config_snapshot=snapshot,
    )
