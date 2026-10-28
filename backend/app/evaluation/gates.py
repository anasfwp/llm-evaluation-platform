"""Evaluate gate rules against per-model run summaries.

Absolute rules need only the run's summaries. Relative rules also need a
baseline run's summaries and each metric's direction; tag-scoped rules need
summaries recomputed over the tagged cases. ``evaluate_report_gate`` builds all
of that from run reports; ``evaluate_gate`` takes the pieces directly.
A missing value never passes silently: the missing-metric policy decides.
"""

from __future__ import annotations

import operator
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field

from app.domain.gates import (
    ERROR_RATE,
    GateConfig,
    GateResult,
    GateRule,
    MissingMetricPolicy,
    RuleOutcome,
    RuleOutcomeStatus,
)
from app.domain.metrics import MetricDirection
from app.domain.models import ModelConfigSnapshot
from app.domain.runs import ModelSummary, RunReport
from app.evaluation.aggregation import summarize_model

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "gte": operator.ge,
    "gt": operator.gt,
    "lte": operator.le,
    "lt": operator.lt,
    "eq": operator.eq,
}
_SYMBOLS = {"gte": ">=", "gt": ">", "lte": "<=", "lt": "<", "eq": "=="}

SummaryLookup = Callable[[str | None], Sequence[ModelSummary]]


@dataclass(frozen=True)
class GateContext:
    """Everything beyond the run's own summaries that some rules need."""

    # Metric name -> direction; required to know which way is "worse" for relative rules.
    directions: Mapping[str, MetricDirection] = field(default_factory=dict)
    baseline: Sequence[ModelSummary] | None = None
    baseline_run_id: str | None = None
    # tag -> candidate (and baseline) summaries over cases carrying that tag.
    tagged: Callable[[str], Sequence[ModelSummary]] | None = None
    baseline_tagged: Callable[[str], Sequence[ModelSummary]] | None = None


def evaluate_gate(
    gate: GateConfig,
    summaries: Sequence[ModelSummary],
    context: GateContext | None = None,
) -> GateResult:
    context = context or GateContext()
    by_name = {summary.model_name: summary for summary in summaries}
    outcomes: list[RuleOutcome] = []
    for rule in gate.rules:
        model_names = [rule.model] if rule.model is not None else list(by_name)
        scoped = _scoped(rule.tag, summaries, context.tagged)
        baseline = (
            _scoped(rule.tag, context.baseline, context.baseline_tagged)
            if context.baseline is not None
            else None
        )
        for model_name in model_names:
            outcomes.append(_evaluate_rule(gate, rule, model_name, scoped, baseline, context))
    return GateResult(
        gate_name=gate.name,
        passed=all(outcome.passed for outcome in outcomes),
        baseline_run_id=context.baseline_run_id,
        results=outcomes,
    )


def evaluate_report_gate(
    gate: GateConfig, report: RunReport, baseline: RunReport | None = None
) -> GateResult:
    """Evaluate a gate on a full run report, optionally against a baseline report."""
    directions = {m.name: m.direction for m in report.metrics}
    context = GateContext(
        directions=directions,
        baseline=baseline.summaries if baseline is not None else None,
        baseline_run_id=baseline.run_id if baseline is not None else None,
        tagged=lambda tag: summaries_for_tag(report, tag),
        baseline_tagged=(lambda tag: summaries_for_tag(baseline, tag)) if baseline else None,
    )
    return evaluate_gate(gate, report.summaries, context)


def summaries_for_tag(report: RunReport, tag: str) -> list[ModelSummary]:
    """Per-model summaries recomputed over the cases carrying ``tag``."""
    from app.evaluation.comparison import metric_shape

    shapes = [metric_shape(info) for info in report.metrics]
    summaries: list[ModelSummary] = []
    for summary in report.summaries:
        results = [
            r for r in report.results if r.model_name == summary.model_name and tag in r.tags
        ]
        if not results:
            continue  # no tagged cases: the rule's value is missing, not zero
        model = ModelConfigSnapshot(
            name=summary.model_name, provider=summary.provider, model_id=summary.model_id
        )
        summaries.append(summarize_model(model, results, shapes))
    return summaries


def _scoped(
    tag: str | None,
    summaries: Sequence[ModelSummary],
    tagged: Callable[[str], Sequence[ModelSummary]] | None,
) -> dict[str, ModelSummary] | None:
    """Summaries by model name for the rule's scope; ``None`` if a tag cannot be resolved."""
    if tag is None:
        return {s.model_name: s for s in summaries}
    if tagged is None:
        return None
    return {s.model_name: s for s in tagged(tag)}


def _label(rule: GateRule) -> str:
    if rule.kind == "absolute":
        assert rule.operator is not None and rule.threshold is not None
        label = f"{rule.metric}.{rule.aggregation} {_SYMBOLS[rule.operator]} {rule.threshold:g}"
    else:
        unit = "%" if rule.regression_unit == "percent" else ""
        label = f"{rule.metric}.{rule.aggregation} regression <= {rule.max_regression:g}{unit}"
    return label + (f" [tag={rule.tag}]" if rule.tag else "")


def _evaluate_rule(
    gate: GateConfig,
    rule: GateRule,
    model_name: str,
    summaries: dict[str, ModelSummary] | None,
    baseline: dict[str, ModelSummary] | None,
    context: GateContext,
) -> RuleOutcome:
    scope = f" for tag '{rule.tag}'" if rule.tag else ""
    if summaries is None:
        actual, missing = None, f"tag-scoped rules need case results{scope}"
    else:
        actual, missing = _lookup(rule, model_name, summaries.get(model_name), scope)

    base_value: float | None = None
    regression: float | None = None
    if rule.kind == "relative" and actual is not None:
        base_value, regression, missing = _relative(
            rule, model_name, summaries, baseline, context, actual, scope
        )

    limit = rule.threshold if rule.kind == "absolute" else rule.max_regression
    assert limit is not None  # guaranteed by GateRule validation

    def outcome(status: RuleOutcomeStatus, reason: str | None = None) -> RuleOutcome:
        return RuleOutcome(
            rule=_label(rule),
            kind=rule.kind,
            metric=rule.metric,
            aggregation=rule.aggregation,
            operator=rule.operator or "max_regression",
            threshold=limit,
            model=model_name,
            tag=rule.tag,
            actual=actual,
            baseline=base_value,
            regression=regression,
            status=status,
            reason=reason,
        )

    if missing:
        policy = rule.missing_metric_policy or gate.missing_metric_policy
        status = {
            MissingMetricPolicy.FAIL: RuleOutcomeStatus.FAILED,
            MissingMetricPolicy.SKIP: RuleOutcomeStatus.SKIPPED,
            MissingMetricPolicy.WARN: RuleOutcomeStatus.WARNED,
        }[policy]
        return outcome(status, f"{missing} (missing_metric_policy={policy})")
    assert actual is not None

    if rule.kind == "absolute":
        assert rule.operator is not None and rule.threshold is not None
        if _OPERATORS[rule.operator](actual, rule.threshold):
            return outcome(RuleOutcomeStatus.PASSED)
        return outcome(
            RuleOutcomeStatus.FAILED,
            f"{rule.metric} {rule.aggregation}{scope} is {actual:g}, "
            f"required {_SYMBOLS[rule.operator]} {rule.threshold:g}",
        )

    assert regression is not None and rule.max_regression is not None
    if regression <= rule.max_regression:
        return outcome(RuleOutcomeStatus.PASSED)
    unit = "%" if rule.regression_unit == "percent" else ""
    return outcome(
        RuleOutcomeStatus.FAILED,
        f"{rule.metric} {rule.aggregation}{scope} regressed by {regression:g}{unit} "
        f"(baseline {base_value:g}, now {actual:g}); allowed {rule.max_regression:g}{unit}",
    )


def _relative(
    rule: GateRule,
    model_name: str,
    summaries: dict[str, ModelSummary] | None,
    baseline: dict[str, ModelSummary] | None,
    context: GateContext,
    actual: float,
    scope: str,
) -> tuple[float | None, float | None, str]:
    """Return ``(baseline_value, regression, missing_reason)``; regression > 0 means worse."""
    if baseline is None:
        return None, None, "no baseline run was provided for this relative rule"
    baseline_name = rule.baseline_model or model_name
    base_summary = baseline.get(baseline_name)
    base_value, missing = _lookup(rule, baseline_name, base_summary, scope, run="baseline")
    if base_value is None:
        return None, None, missing
    if rule.metric != ERROR_RATE:
        current = summaries.get(model_name) if summaries else None
        before = base_summary.metrics.get(rule.metric) if base_summary else None
        after = current.metrics.get(rule.metric) if current else None
        if (
            before is not None
            and after is not None
            and before.metric_version != after.metric_version
        ):
            return (
                base_value,
                None,
                (
                    f"metric '{rule.metric}' version differs from the baseline "
                    f"({before.metric_version} vs {after.metric_version})"
                ),
            )
    direction = (
        MetricDirection.LOWER_IS_BETTER
        if rule.metric == ERROR_RATE
        else context.directions.get(rule.metric)
    )
    if direction is None:
        return base_value, None, f"direction of metric '{rule.metric}' is unknown"
    worse_by = (
        actual - base_value if direction == MetricDirection.LOWER_IS_BETTER else base_value - actual
    )
    if rule.regression_unit == "absolute":
        return base_value, worse_by, ""
    if base_value == 0:
        # Any worsening from zero is an infinite relative change; no change is 0%.
        return base_value, (0.0 if worse_by <= 0 else float("inf")), ""
    return base_value, worse_by / abs(base_value) * 100, ""


def _lookup(
    rule: GateRule,
    model_name: str,
    summary: ModelSummary | None,
    scope: str = "",
    run: str = "run",
) -> tuple[float | None, str]:
    if summary is None:
        return None, f"model '{model_name}' not found in {run}{scope}"
    if rule.metric == ERROR_RATE:
        return summary.error_rate, ""
    metric = summary.metrics.get(rule.metric)
    if metric is None:
        return None, f"metric '{rule.metric}' was not computed for model '{model_name}' in {run}"
    if rule.aggregation == "count":
        return float(metric.scored_count), ""
    if metric.scored_count == 0:
        return None, (
            f"metric '{rule.metric}' has no scored cases for model '{model_name}' in {run}{scope}"
        )
    value: float | None = getattr(metric, rule.aggregation)
    if value is None:
        return None, f"metric '{rule.metric}' does not report aggregation '{rule.aggregation}'"
    return value, ""
