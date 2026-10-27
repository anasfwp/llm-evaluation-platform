"""Evaluate absolute-threshold gate rules against per-model run summaries."""

from __future__ import annotations

import operator
from collections.abc import Callable, Sequence

from app.domain.gates import (
    ERROR_RATE,
    GateConfig,
    GateResult,
    GateRule,
    MissingMetricPolicy,
    RuleOutcome,
    RuleOutcomeStatus,
)
from app.domain.runs import ModelSummary

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "gte": operator.ge,
    "gt": operator.gt,
    "lte": operator.le,
    "lt": operator.lt,
    "eq": operator.eq,
}
_SYMBOLS = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "=="}


def evaluate_gate(gate: GateConfig, summaries: Sequence[ModelSummary]) -> GateResult:
    by_name = {summary.model_name: summary for summary in summaries}
    outcomes: list[RuleOutcome] = []
    for rule in gate.rules:
        model_names = [rule.model] if rule.model is not None else list(by_name)
        for model_name in model_names:
            outcomes.append(_evaluate_rule(gate, rule, model_name, by_name.get(model_name)))
    return GateResult(
        gate_name=gate.name,
        passed=all(outcome.passed for outcome in outcomes),
        results=outcomes,
    )


def _evaluate_rule(
    gate: GateConfig, rule: GateRule, model_name: str, summary: ModelSummary | None
) -> RuleOutcome:
    label = f"{rule.metric}.{rule.aggregation} {_SYMBOLS[rule.operator]} {rule.threshold:g}"
    actual, missing_reason = _lookup(rule, model_name, summary)

    def outcome(status: RuleOutcomeStatus, reason: str | None = None) -> RuleOutcome:
        return RuleOutcome(
            rule=label,
            metric=rule.metric,
            aggregation=rule.aggregation,
            operator=rule.operator,
            threshold=rule.threshold,
            model=model_name,
            actual=actual,
            status=status,
            reason=reason,
        )

    if actual is None:
        policy = rule.missing_metric_policy or gate.missing_metric_policy
        status = {
            MissingMetricPolicy.FAIL: RuleOutcomeStatus.FAILED,
            MissingMetricPolicy.SKIP: RuleOutcomeStatus.SKIPPED,
            MissingMetricPolicy.WARN: RuleOutcomeStatus.WARNED,
        }[policy]
        return outcome(status, f"{missing_reason} (missing_metric_policy={policy})")

    if _OPERATORS[rule.operator](actual, rule.threshold):
        return outcome(RuleOutcomeStatus.PASSED)
    return outcome(
        RuleOutcomeStatus.FAILED,
        f"{rule.metric} {rule.aggregation} is {actual:g}, "
        f"required {_SYMBOLS[rule.operator]} {rule.threshold:g}",
    )


def _lookup(
    rule: GateRule, model_name: str, summary: ModelSummary | None
) -> tuple[float | None, str]:
    if summary is None:
        return None, f"model '{model_name}' not found in run"
    if rule.metric == ERROR_RATE:
        return summary.error_rate, ""
    metric = summary.metrics.get(rule.metric)
    if metric is None:
        return None, f"metric '{rule.metric}' was not computed for model '{model_name}'"
    if rule.aggregation == "count":
        return float(metric.scored_count), ""
    if metric.scored_count == 0:
        return None, f"metric '{rule.metric}' has no scored cases for model '{model_name}'"
    value: float | None = getattr(metric, rule.aggregation)
    if value is None:
        return None, f"metric '{rule.metric}' does not report aggregation '{rule.aggregation}'"
    return value, ""
