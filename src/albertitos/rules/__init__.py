"""Motor de reglas determinista y puro: mismos inputs + misma config ⇒ misma salida."""

from .base import Rule, RuleContext, RuleEvaluation
from .engine import evaluate
from .rules import RULE_CODES, all_rules

__all__ = ["RULE_CODES", "Rule", "RuleContext", "RuleEvaluation", "all_rules", "evaluate"]
