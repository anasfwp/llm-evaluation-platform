from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.gates import GateConfig, GateRule, RuleOutcomeStatus
from app.domain.runs import MetricSummary, ModelSummary, UsageSummary
from app.evaluation.gates import evaluate_gate


def _summary(name: str = "m1", error_rate: float = 0.0, **metrics: MetricSummary) -> ModelSummary:
    return ModelSummary(
        model_name=name,
        provider="fake",
        model_id="fake-1",
        case_count=20,
        success_count=20,
        error_count=0,
        error_rate=error_rate,
        error_codes={},
        usage=UsageSummary(cases_with_usage=0, input_tokens_total=0, output_tokens_total=0),
        metrics=metrics,
    )


def _stats(mean: float | None, p95: float | None = None, scored: int = 20) -> MetricSummary:
    return MetricSummary(
        metric_version="1.0",
        scored_count=scored,
        not_applicable_count=0,
        error_count=0,
        mean=mean,
        median=mean,
        p95=p95 if p95 is not None else mean,
        min=mean,
        max=mean,
        small_sample=False,
    )


def _gate(*rules: dict[str, Any], policy: str = "fail") -> GateConfig:
    return GateConfig.model_validate({"missing_metric_policy": policy, "rules": list(rules)})


EM_RULE = {"metric": "exact_match", "aggregation": "mean", "operator": "gte", "threshold": 0.8}


@pytest.mark.parametrize(
    ("operator", "actual", "passed"),
    [
        ("gte", 0.8, True),
        ("gte", 0.79, False),
        ("gt", 0.8, False),
        ("lte", 0.8, True),
        ("lt", 0.8, False),
        ("eq", 0.8, True),
    ],
)
def test_operators(operator: str, actual: float, passed: bool) -> None:
    gate = _gate({**EM_RULE, "operator": operator})
    result = evaluate_gate(gate, [_summary(exact_match=_stats(actual))])
    assert result.passed is passed
    assert result.results[0].actual == actual


def test_failed_rule_has_machine_readable_reason() -> None:
    result = evaluate_gate(_gate(EM_RULE), [_summary(exact_match=_stats(0.5))])
    outcome = result.results[0]
    assert result.passed is False
    assert outcome.status == RuleOutcomeStatus.FAILED
    assert outcome.metric == "exact_match"
    assert outcome.threshold == 0.8
    assert outcome.reason is not None and "0.5" in outcome.reason


def test_rule_applies_to_every_model_unless_scoped() -> None:
    summaries = [
        _summary("good", exact_match=_stats(0.9)),
        _summary("bad", exact_match=_stats(0.1)),
    ]
    result = evaluate_gate(_gate(EM_RULE), summaries)
    assert [(o.model, o.passed) for o in result.results] == [("good", True), ("bad", False)]
    assert result.passed is False

    scoped = evaluate_gate(_gate({**EM_RULE, "model": "good"}), summaries)
    assert scoped.passed is True
    assert [o.model for o in scoped.results] == ["good"]


def test_error_rate_and_p95_rules() -> None:
    gate = _gate(
        {"metric": "error_rate", "aggregation": "overall", "operator": "lte", "threshold": 0.02},
        {"metric": "latency", "aggregation": "p95", "operator": "lte", "threshold": 2500},
    )
    result = evaluate_gate(gate, [_summary(error_rate=0.05, latency=_stats(800, p95=1400))])
    assert [o.passed for o in result.results] == [False, True]


@pytest.mark.parametrize(
    ("policy", "status", "passed"),
    [
        ("fail", RuleOutcomeStatus.FAILED, False),
        ("skip", RuleOutcomeStatus.SKIPPED, True),
        ("warn", RuleOutcomeStatus.WARNED, True),
    ],
)
def test_missing_metric_policy(policy: str, status: RuleOutcomeStatus, passed: bool) -> None:
    result = evaluate_gate(_gate(EM_RULE, policy=policy), [_summary()])
    assert result.results[0].status == status
    assert result.passed is passed
    assert result.results[0].actual is None


def test_metric_with_no_scored_cases_counts_as_missing() -> None:
    summary = _summary(exact_match=_stats(None, scored=0))
    assert evaluate_gate(_gate(EM_RULE), [summary]).passed is False


def test_per_rule_policy_overrides_gate_policy() -> None:
    gate = _gate({**EM_RULE, "missing_metric_policy": "skip"}, policy="fail")
    assert evaluate_gate(gate, [_summary()]).passed is True


def test_unknown_model_in_rule_follows_missing_policy() -> None:
    result = evaluate_gate(_gate({**EM_RULE, "model": "ghost"}), [_summary()])
    assert result.passed is False
    assert "not found" in (result.results[0].reason or "")


def test_rule_validation() -> None:
    with pytest.raises(ValidationError):
        GateRule.model_validate({**EM_RULE, "aggregation": "overall"})
    with pytest.raises(ValidationError):
        GateRule.model_validate({**EM_RULE, "metric": "error_rate"})
    with pytest.raises(ValidationError):
        GateRule.model_validate({**EM_RULE, "operator": "approximately"})
    with pytest.raises(ValidationError):
        GateConfig.model_validate({"rules": []})
