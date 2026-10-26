from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from app.domain.datasets import Dataset
from app.domain.metrics import MetricCategory, MetricDirection, MetricResult, MetricStatus
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.domain.runs import CaseStatus, EvalConfig, RunReport, RunStatus
from app.evaluation.engine import RunPlan, run_evaluation
from app.evaluation.metrics.base import Metric, MetricInput
from app.evaluation.metrics.exact_match import ExactMatch
from app.evaluation.metrics.latency import Latency
from app.providers.base import ModelAdapter, ProviderError
from app.providers.fake import FakeProvider


def _ok(request: ModelRequest, text: str = "ok") -> NormalizedModelResponse:
    return NormalizedModelResponse(output_text=text, provider="test", model_id="t")


class ScriptedAdapter:
    """Raises the scripted exceptions for a case in order, then answers 'ok'."""

    def __init__(self, script: dict[str, list[Exception]] | None = None, delay: float = 0) -> None:
        self.script = {key: list(errors) for key, errors in (script or {}).items()}
        self.delay = delay
        self.calls: dict[str, int] = {}
        self.in_flight = 0
        self.max_in_flight = 0

    async def generate(
        self, *, request: ModelRequest, model_config: ModelConfigSnapshot, timeout_seconds: float
    ) -> NormalizedModelResponse:
        self.calls[request.case_key] = self.calls.get(request.case_key, 0) + 1
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay)
            pending = self.script.get(request.case_key)
            if pending:
                raise pending.pop(0)
            return _ok(request)
        finally:
            self.in_flight -= 1


def _run(
    config: EvalConfig,
    dataset: Dataset,
    adapters: dict[str, ModelAdapter],
    metrics: list[Metric] | None = None,
) -> RunReport:
    plan = RunPlan(
        config=config,
        dataset=dataset,
        dataset_source="dataset.json",
        metrics=metrics or [ExactMatch(), Latency()],
        adapters=adapters,
    )
    return asyncio.run(run_evaluation(plan))


def _rate_limited() -> ProviderError:
    return ProviderError(ProviderErrorCategory.RATE_LIMITED, "slow down")


def test_fake_run_scores_every_case_in_dataset_order(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    dataset = make_dataset(count=5)
    config = make_config()
    model = config.models[0]
    report = _run(config, dataset, {"m1": FakeProvider.from_config(model, dataset=dataset)})

    assert report.status == RunStatus.COMPLETED
    assert [r.case_key for r in report.results] == [c.case_key for c in dataset.cases]
    assert all(r.status == CaseStatus.SUCCESS for r in report.results)
    summary = report.summaries[0]
    assert summary.metrics["exact_match"].mean == 1.0
    assert summary.metrics["latency"].scored_count == 5
    assert report.dataset.content_hash == dataset.content_hash()
    assert report.config_hash == config.config_hash()
    assert [m.name for m in report.metrics] == ["exact_match", "latency"]


def test_transient_error_is_retried_then_succeeds(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = ScriptedAdapter({"case-0": [_rate_limited()]})
    report = _run(make_config(max_retries=1), make_dataset(count=1), {"m1": adapter})
    result = report.results[0]
    assert result.status == CaseStatus.SUCCESS
    assert result.attempts == 2
    assert adapter.calls["case-0"] == 2


def test_retries_are_bounded(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = ScriptedAdapter({"case-0": [_rate_limited() for _ in range(5)]})
    report = _run(make_config(max_retries=2), make_dataset(count=1), {"m1": adapter})
    result = report.results[0]
    assert result.status == CaseStatus.ERROR
    assert result.error_code == "rate_limited"
    assert result.attempts == 3
    assert adapter.calls["case-0"] == 3


def test_non_transient_error_is_not_retried(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    error = ProviderError(ProviderErrorCategory.AUTHENTICATION_FAILED, "bad key")
    adapter = ScriptedAdapter({"case-0": [error]})
    report = _run(make_config(max_retries=3), make_dataset(count=1), {"m1": adapter})
    assert report.results[0].error_code == "authentication_failed"
    assert adapter.calls["case-0"] == 1


def test_timeout_is_recorded_as_timeout_error(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = ScriptedAdapter(delay=1.0)
    config = make_config(timeout_seconds=0.05, max_retries=0)
    report = _run(config, make_dataset(count=1), {"m1": adapter})
    result = report.results[0]
    assert result.status == CaseStatus.ERROR
    assert result.error_code == "timeout"
    assert result.actual_output is None


def test_partial_failure_preserves_other_results(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    error = ProviderError(ProviderErrorCategory.INVALID_REQUEST, "bad input")
    report = _run(
        make_config(), make_dataset(count=3), {"m1": ScriptedAdapter({"case-1": [error]})}
    )
    statuses = {r.case_key: r.status for r in report.results}
    assert statuses == {
        "case-0": CaseStatus.SUCCESS,
        "case-1": CaseStatus.ERROR,
        "case-2": CaseStatus.SUCCESS,
    }
    failed = report.results[1]
    assert {m.status for m in failed.metrics} == {MetricStatus.NOT_APPLICABLE}
    assert report.summaries[0].error_rate == 1 / 3


def test_unexpected_adapter_exception_is_contained_and_redacted(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    crash = RuntimeError("upstream said api_key=sk-test-1234567890abcdef is invalid")
    report = _run(
        make_config(), make_dataset(count=2), {"m1": ScriptedAdapter({"case-0": [crash]})}
    )
    result = report.results[0]
    assert result.error_code == "unknown_error"
    assert result.error_message is not None
    assert "sk-test-1234567890abcdef" not in result.error_message
    assert report.results[1].status == CaseStatus.SUCCESS


def test_concurrency_is_bounded(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = ScriptedAdapter(delay=0.02)
    _run(make_config(max_concurrency=2), make_dataset(count=8), {"m1": adapter})
    assert adapter.max_in_flight == 2


def test_broken_metric_is_reported_as_error_without_losing_case(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    class Broken(Metric):
        name = "broken"
        version = "0.1"
        category = MetricCategory.ANSWER_QUALITY
        direction = MetricDirection.HIGHER_IS_BETTER
        score_range = (0.0, 1.0)
        required_inputs = ()
        description = "always raises"

        def evaluate(self, data: MetricInput) -> MetricResult:
            raise ZeroDivisionError("boom")

    report = _run(
        make_config(), make_dataset(count=1), {"m1": ScriptedAdapter()}, [Broken(), Latency()]
    )
    by_name = {m.metric_name: m for m in report.results[0].metrics}
    assert by_name["broken"].status == MetricStatus.ERROR
    assert by_name["latency"].status == MetricStatus.SCORED
    assert report.summaries[0].metrics["broken"].error_count == 1


def test_multiple_models_are_summarized_separately(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    models: list[dict[str, Any]] = [
        {"name": "good", "provider": "fake", "model_id": "a"},
        {
            "name": "bad",
            "provider": "fake",
            "model_id": "b",
            "parameters": {"mode": "constant", "constant_output": "nope"},
        },
    ]
    config = make_config(models=models)
    dataset = make_dataset(count=4)
    adapters: dict[str, ModelAdapter] = {
        m.name: FakeProvider.from_config(m, dataset=dataset) for m in config.models
    }
    report = _run(config, dataset, adapters)
    means = {s.model_name: s.metrics["exact_match"].mean for s in report.summaries}
    assert means == {"good": 1.0, "bad": 0.0}
    assert len(report.results) == 8
