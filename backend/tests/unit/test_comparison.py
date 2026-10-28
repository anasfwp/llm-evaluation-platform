from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest

from app.domain.comparison import CaseState, ComparisonSettings, ModelPair, Verdict
from app.domain.datasets import Dataset
from app.domain.gates import GateConfig, GateRule, RuleOutcomeStatus
from app.domain.runs import EvalConfig, RunReport
from app.evaluation.comparison import ComparisonError, compare_runs
from app.evaluation.engine import RunPlan, run_evaluation
from app.evaluation.gates import evaluate_report_gate
from app.evaluation.registry import build_metric
from app.evaluation.reporting import render_comparison_markdown, render_markdown
from app.providers.fake import FakeProvider

DatasetFactory = Callable[..., Dataset]
ConfigFactory = Callable[..., EvalConfig]


def _run(
    make_config: ConfigFactory,
    dataset: Dataset,
    *,
    name: str = "m1",
    metrics: list[str] | None = None,
    **parameters: Any,
) -> RunReport:
    config = make_config(
        models=[{"name": name, "provider": "fake", "model_id": "fake-1", "parameters": parameters}],
        metrics=metrics or ["exact_match", "token_f1", "latency"],
    )
    plan = RunPlan(
        config=config,
        dataset=dataset,
        dataset_source="dataset.json",
        metrics=[build_metric(m.name, m.version, m.config) for m in config.metrics],
        adapters={m.name: FakeProvider.from_config(m, dataset=dataset) for m in config.models},
    )
    return asyncio.run(run_evaluation(plan))


@pytest.fixture
def dataset(make_dataset: DatasetFactory) -> Dataset:
    return make_dataset(count=4)


def test_identical_runs_have_no_regressions(make_config: ConfigFactory, dataset: Dataset) -> None:
    baseline = _run(make_config, dataset)
    candidate = _run(make_config, dataset)
    comparison = compare_runs(baseline, candidate)
    assert comparison.same_dataset
    assert not comparison.regressed
    model = comparison.models[0]
    assert model.cases_compared == 4
    em = next(d for d in model.metrics if d.metric == "exact_match")
    assert em.verdict == Verdict.UNCHANGED
    assert model.newly_failing == [] and model.score_changes == []


def test_detects_newly_failing_recovered_and_score_drops(
    make_config: ConfigFactory, dataset: Dataset
) -> None:
    baseline = _run(make_config, dataset, overrides={"case-0": {"output": "wrong"}})
    candidate = _run(
        make_config,
        dataset,
        overrides={"case-1": {"output": "nope"}, "case-2": {"error": "invalid_request"}},
    )
    comparison = compare_runs(baseline, candidate)
    model = comparison.models[0]
    assert {c.case_key for c in model.newly_failing} == {"case-1", "case-2"}
    assert [c.case_key for c in model.recovered] == ["case-0"]
    errored = next(c for c in model.newly_failing if c.case_key == "case-2")
    assert errored.candidate_reasons == ["error: invalid_request"]
    assert model.error_rate.verdict == Verdict.REGRESSED
    drops = [c for c in model.score_changes if c.verdict == "regressed"]
    assert {(c.case_key, c.metric) for c in drops} == {
        ("case-1", "exact_match"),
        ("case-1", "token_f1"),
    }
    assert comparison.regressed
    assert comparison.newly_failing_count == 2 and comparison.recovered_count == 1
    dumped = comparison.model_dump(mode="json")
    assert dumped["regressed"] is True and dumped["models"][0]["regressed"] is True


def test_latency_changes_alone_do_not_count_as_regression(
    make_config: ConfigFactory, dataset: Dataset
) -> None:
    comparison = compare_runs(_run(make_config, dataset), _run(make_config, dataset, latency_ms=30))
    latency = next(d for d in comparison.models[0].metrics if d.metric == "latency")
    assert latency.verdict == Verdict.REGRESSED
    assert not comparison.regressed


def test_metrics_with_different_config_or_missing_are_excluded(
    make_config: ConfigFactory, dataset: Dataset
) -> None:
    baseline = _run(make_config, dataset, metrics=["exact_match", "latency"])
    candidate = _run(make_config, dataset, metrics=["exact_match", "token_f1"])
    comparison = compare_runs(baseline, candidate)
    assert comparison.excluded_metrics == {
        "token_f1": "not computed in the baseline run",
        "latency": "not computed in the candidate run",
    }
    assert {d.metric for d in comparison.models[0].metrics} == {"exact_match"}


def test_cases_are_aligned_by_key_when_datasets_differ(
    make_config: ConfigFactory, make_dataset: DatasetFactory, make_case: Callable[..., Any]
) -> None:
    old = make_dataset(make_case("a", "x"), make_case("b", "y"))
    new = make_dataset(make_case("b", "y"), make_case("c", "z"))
    comparison = compare_runs(_run(make_config, old), _run(make_config, new))
    model = comparison.models[0]
    assert not comparison.same_dataset
    assert model.cases_compared == 1
    assert model.cases_only_in_baseline == ["a"] and model.cases_only_in_candidate == ["c"]
    assert any("different dataset content" in w for w in comparison.warnings)


def test_model_pairs(make_config: ConfigFactory, dataset: Dataset) -> None:
    baseline = _run(make_config, dataset, name="old")
    candidate = _run(make_config, dataset, name="new")
    with pytest.raises(ComparisonError, match="no model names in common"):
        compare_runs(baseline, candidate)
    paired = compare_runs(
        baseline,
        candidate,
        ComparisonSettings(model_pairs=[ModelPair(baseline="old", candidate="new")]),
    )
    assert paired.models[0].baseline_model == "old"
    with pytest.raises(ComparisonError, match="not in the baseline"):
        compare_runs(
            baseline,
            candidate,
            ComparisonSettings(model_pairs=[ModelPair(baseline="x", candidate="new")]),
        )


def test_open_ended_cases_are_unknown_not_failing(
    make_config: ConfigFactory, make_dataset: DatasetFactory, make_case: Callable[..., Any]
) -> None:
    data = make_dataset(make_case("open", None))
    comparison = compare_runs(_run(make_config, data), _run(make_config, data))
    assert comparison.models[0].newly_failing == []
    report = _run(make_config, data)
    assert "## Failed cases (0)" in render_markdown(report)


def test_comparison_markdown(make_config: ConfigFactory, dataset: Dataset) -> None:
    baseline = _run(make_config, dataset)
    candidate = _run(make_config, dataset, overrides={"case-1": {"output": "nope"}})
    text = render_comparison_markdown(compare_runs(baseline, candidate))
    assert "REGRESSED" in text
    assert "`case-1`" in text
    assert "| exact_match mean | 1 | 0.75 | -0.25 | regressed ⚠ |" in text


# Relative and tag-scoped gates


def _gate(*rules: dict[str, Any], policy: str = "fail") -> GateConfig:
    return GateConfig.model_validate({"missing_metric_policy": policy, "rules": list(rules)})


REL_EM = {"metric": "exact_match", "aggregation": "mean", "kind": "relative", "max_regression": 0.1}


def test_relative_rule_passes_within_budget_and_fails_beyond(
    make_config: ConfigFactory, dataset: Dataset
) -> None:
    baseline = _run(make_config, dataset)
    worse = _run(make_config, dataset, overrides={"case-1": {"output": "nope"}})
    outcome = evaluate_report_gate(_gate(REL_EM), worse, baseline).results[0]
    assert outcome.status == RuleOutcomeStatus.FAILED
    assert (outcome.baseline, outcome.actual, outcome.regression) == (1.0, 0.75, 0.25)
    assert "regressed by 0.25" in (outcome.reason or "")
    loose = evaluate_report_gate(_gate({**REL_EM, "max_regression": 0.3}), worse, baseline)
    assert loose.passed
    assert loose.baseline_run_id == baseline.run_id


def test_relative_percent_rule_uses_metric_direction(
    make_config: ConfigFactory, dataset: Dataset
) -> None:
    baseline = _run(make_config, dataset, latency_ms=10)
    slower = _run(make_config, dataset, latency_ms=40)
    rule = {
        "metric": "latency",
        "aggregation": "mean",
        "kind": "relative",
        "max_regression": 50,
        "regression_unit": "percent",
    }
    result = evaluate_report_gate(_gate(rule), slower, baseline)
    assert not result.passed
    assert result.results[0].regression is not None and result.results[0].regression > 50
    # Faster is an improvement: negative regression passes.
    assert evaluate_report_gate(_gate(rule), baseline, slower).passed


def test_relative_rule_without_baseline_uses_missing_policy(
    make_config: ConfigFactory, dataset: Dataset
) -> None:
    report = _run(make_config, dataset)
    failed = evaluate_report_gate(_gate(REL_EM), report)
    assert failed.results[0].status == RuleOutcomeStatus.FAILED
    assert "no baseline" in (failed.results[0].reason or "")
    assert evaluate_report_gate(_gate(REL_EM, policy="skip"), report).passed


def test_relative_error_rate(make_config: ConfigFactory, dataset: Dataset) -> None:
    baseline = _run(make_config, dataset)
    errors = _run(make_config, dataset, overrides={"case-0": {"error": "invalid_request"}})
    rule = {
        "metric": "error_rate",
        "aggregation": "overall",
        "kind": "relative",
        "max_regression": 0,
    }
    outcome = evaluate_report_gate(_gate(rule), errors, baseline).results[0]
    assert outcome.status == RuleOutcomeStatus.FAILED
    assert outcome.regression == 0.25


def test_tag_scoped_rule(
    make_config: ConfigFactory, make_dataset: DatasetFactory, make_case: Callable[..., Any]
) -> None:
    data = make_dataset(
        make_case("g1", "Paris", tags=["geo"]),
        make_case("g2", "Rome", tags=["geo"]),
        make_case("m1", "4", tags=["math"]),
    )
    report = _run(make_config, data, overrides={"m1": {"output": "5"}})
    rule = {"metric": "exact_match", "aggregation": "mean", "operator": "gte", "threshold": 1.0}
    assert evaluate_report_gate(_gate({**rule, "tag": "geo"}), report).passed
    math = evaluate_report_gate(_gate({**rule, "tag": "math"}), report).results[0]
    assert math.status == RuleOutcomeStatus.FAILED
    assert math.rule.endswith("[tag=math]")
    missing = evaluate_report_gate(_gate({**rule, "tag": "nope"}), report).results[0]
    assert missing.status == RuleOutcomeStatus.FAILED
    assert "not found" in (missing.reason or "")


def test_rule_validation() -> None:
    with pytest.raises(ValueError, match="max_regression"):
        GateRule.model_validate({"metric": "x", "aggregation": "mean", "kind": "relative"})
    with pytest.raises(ValueError, match="operator"):
        GateRule.model_validate({"metric": "x", "aggregation": "mean"})
    with pytest.raises(ValueError, match="not operator"):
        GateRule.model_validate({**REL_EM, "operator": "gte", "threshold": 1})
    with pytest.raises(ValueError, match="only for relative"):
        GateRule.model_validate(
            {"metric": "x", "aggregation": "mean", "operator": "gte", "threshold": 1,
             "max_regression": 1}
        )  # fmt: skip
    assert _gate(REL_EM).needs_baseline
    assert CaseState.PASS == "pass"
