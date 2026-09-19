"""Motor de decisión: determinista y puro. Sin I/O, sin reloj, sin azar.

Mismos campos + misma config + mismo maestro ⇒ misma salida, byte a byte.
Política de agregación (docs/normas.md + AGENTS.md §6):
  - cada FAIL resuelve al resultado configurado para su regla (`outcomes.on_fail`),
    por defecto NO_PAGAR; una regla rota nunca puede resolver PAGAR.
  - si algún FAIL resuelve NO_PAGAR ⇒ NO_PAGAR (negativo definitivo, inmune a juicio humano)
  - si no, si hay algún FAIL que escala, algún UNKNOWN o no hay reglas ⇒ ESCALAR
  - si no, todo PASS ⇒ PAGAR
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
    ctx = RuleContext(fields=fields, master=master, thresholds=rule_config.thresholds, seleccion=rule_config.seleccion)
    enabled = set(rule_config.enabled_codes)
    rules = sorted(
        (r for r in all_rules() if not enabled or r.code in enabled), key=lambda r: r.code
    )

    evaluations = [rule.evaluate(ctx) for rule in rules]
    rule_outcomes = {r.code: rule_config.on_fail(r.code).value for r in rules}

    fail_results = [
        rule_config.on_fail(e.code) for e in evaluations if e.verdict is RuleVerdict.FAIL
    ]
    if Result.NO_PAGAR in fail_results:
        result = Result.NO_PAGAR
    elif fail_results or not evaluations or any(
        e.verdict is RuleVerdict.UNKNOWN for e in evaluations
    ):
        result = Result.ESCALAR
    else:
        result = Result.PAGAR

    snapshot = ConfigSnapshot(
        thresholds=rule_config.thresholds,
        extractor_versions=extractor_versions or {},
        master_sha256=master.sha256,
        config_version=rule_config.version,
        rule_outcomes=rule_outcomes,
    )
    return Decision(
        invoice_id=invoice_id,
        file_id=file_id,
        result=result,
        rule_evaluations=evaluations,
        config_snapshot=snapshot,
    )
