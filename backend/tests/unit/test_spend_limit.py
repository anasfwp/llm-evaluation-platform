from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.cli.main import EXIT_OK, EXIT_RUN_FAILED, main
from app.core.errors import InputValidationError
from app.domain.datasets import Dataset
from app.domain.metrics import MetricStatus
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.domain.runs import EvalConfig, RunReport, RunStatus
from app.evaluation.engine import RunPlan, run_evaluation
from app.evaluation.loader import load_config
from app.evaluation.metrics.base import Metric
from app.evaluation.metrics.exact_match import ExactMatch
from app.evaluation.metrics.llm_judge import JudgeRelevance
from app.evaluation.metrics.semantic_similarity import SemanticSimilarity
from app.evaluation.pricing import default_pricing
from app.evaluation.spend import SpendTracker, unpriced_models
from app.providers.base import ModelAdapter, ProviderError

# 1000 input + 1000 output tokens per call, at the fake provider's $1 and $2 per million.
COST_PER_CALL = 0.003


class MeteredAdapter:
    """Answers every case with fixed usage, after raising any scripted errors."""

    def __init__(self, tokens: int | None = 1000, errors: list[Exception] | None = None) -> None:
        self.tokens = tokens
        self.errors = list(errors or [])
        self.calls = 0

    async def generate(
        self, *, request: ModelRequest, model_config: ModelConfigSnapshot, timeout_seconds: float
    ) -> NormalizedModelResponse:
        self.calls += 1
        await asyncio.sleep(0)  # Let concurrent cases start, as a real network call would.
        if self.errors:
            raise self.errors.pop(0)
        return NormalizedModelResponse(
            output_text="ok",
            provider=model_config.provider,
            model_id=model_config.model_id,
            input_tokens=self.tokens,
            output_tokens=self.tokens,
        )


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
        metrics=metrics or [ExactMatch()],
        adapters=adapters,
    )
    return asyncio.run(run_evaluation(plan))


def _judge() -> JudgeRelevance:
    return JudgeRelevance(
        {"judge": {"provider": "fake", "model_id": "judge", "parameters": {"mode": "judge"}}}
    )


def test_run_without_a_limit_is_not_tracked(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    # No usage reported, which would stop a run that had a limit.
    report = _run(make_config(), make_dataset(count=3), {"m1": MeteredAdapter(tokens=None)})
    assert report.status == RunStatus.COMPLETED
    assert report.spend is None
    assert len(report.results) == 3


def test_limit_above_actual_spend_completes(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    config = make_config(max_spend_usd=1.0, max_concurrency=1)
    report = _run(config, make_dataset(count=3), {"m1": MeteredAdapter()})
    assert report.status == RunStatus.COMPLETED
    assert report.spend is not None
    assert report.spend.estimated_usd == pytest.approx(3 * COST_PER_CALL)
    assert report.spend.stop_reason is None


def test_limit_stops_remaining_cases_and_keeps_results(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = MeteredAdapter()
    config = make_config(max_spend_usd=COST_PER_CALL * 2, max_concurrency=1)
    report = _run(config, make_dataset(count=5), {"m1": adapter})

    assert adapter.calls == 2
    assert report.status == RunStatus.CANCELLED
    assert len(report.results) == 2
    assert report.spend is not None
    assert report.spend.estimated_usd == pytest.approx(COST_PER_CALL * 2)
    assert report.spend.stop_reason is not None
    assert "limit" in report.spend.stop_reason


def test_reaching_the_limit_on_the_last_case_still_completes(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    # Nothing was skipped, so the results are complete and may be compared.
    config = make_config(max_spend_usd=COST_PER_CALL * 2, max_concurrency=1)
    report = _run(config, make_dataset(count=2), {"m1": MeteredAdapter()})
    assert report.status == RunStatus.COMPLETED
    assert report.spend is not None
    assert report.spend.stop_reason is None


def test_limit_is_shared_across_models(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    first, second = MeteredAdapter(), MeteredAdapter()
    config = make_config(
        models=[
            {"name": "m1", "provider": "fake", "model_id": "a"},
            {"name": "m2", "provider": "fake", "model_id": "b"},
        ],
        max_spend_usd=COST_PER_CALL * 2,
        max_concurrency=1,
    )
    report = _run(config, make_dataset(count=2), {"m1": first, "m2": second})
    assert (first.calls, second.calls) == (2, 0)
    assert report.status == RunStatus.CANCELLED


def test_in_flight_overshoot_is_bounded_by_concurrency(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = MeteredAdapter()
    config = make_config(max_spend_usd=COST_PER_CALL / 2, max_concurrency=3)
    report = _run(config, make_dataset(count=9), {"m1": adapter})
    # Three calls start together before the first one's cost is known; no more start after.
    assert adapter.calls == 3
    assert report.status == RunStatus.CANCELLED


def test_judge_calls_count_and_are_skipped_at_the_limit(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    # The model call alone stays under the limit, so the judge is what ends the run.
    config = make_config(max_spend_usd=COST_PER_CALL + 0.000001, max_concurrency=1)
    judge = _judge()
    report = _run(config, make_dataset(count=3), {"m1": MeteredAdapter()}, [ExactMatch(), judge])

    assert report.status == RunStatus.CANCELLED
    assert report.spend is not None
    assert report.spend.estimated_usd > COST_PER_CALL + 0.000001
    assert len(report.results) == 1
    assert report.results[0].metrics[1].status == MetricStatus.SCORED


def test_judge_is_skipped_once_the_model_call_reaches_the_limit(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    config = make_config(max_spend_usd=COST_PER_CALL / 2, max_concurrency=1)
    report = _run(config, make_dataset(count=1), {"m1": MeteredAdapter()}, [ExactMatch(), _judge()])

    # Even with every case attempted, a skipped judge leaves the results partial.
    assert report.status == RunStatus.CANCELLED
    exact, judge = report.results[0].metrics
    assert exact.status == MetricStatus.SCORED
    assert judge.status == MetricStatus.ERROR
    assert judge.details["error_code"] == "spend_limit_reached"


def test_missing_usage_stops_the_run(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = MeteredAdapter(tokens=None)
    config = make_config(max_spend_usd=1.0, max_concurrency=1)
    report = _run(config, make_dataset(count=4), {"m1": adapter})

    assert adapter.calls == 1
    assert report.status == RunStatus.CANCELLED
    assert report.spend is not None
    assert report.spend.stop_reason is not None
    assert "did not report token usage" in report.spend.stop_reason


def test_retries_stop_once_the_limit_is_reached(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    tracker = SpendTracker(1.0, default_pricing())

    class SpendsThenFails:
        """Stands in for a concurrent case reaching the limit during this case's first attempt."""

        calls = 0

        async def generate(self, **_: Any) -> NormalizedModelResponse:
            self.calls += 1
            tracker.spent_usd = 1.0
            raise ProviderError(ProviderErrorCategory.RATE_LIMITED, "slow down")

    adapter = SpendsThenFails()
    plan = RunPlan(
        config=make_config(max_spend_usd=1.0, max_retries=3, max_concurrency=1),
        dataset=make_dataset(count=1),
        dataset_source="dataset.json",
        metrics=[ExactMatch()],
        adapters={"m1": adapter},
    )
    report = asyncio.run(run_evaluation(plan, spend=tracker))

    assert adapter.calls == 1
    assert report.status == RunStatus.CANCELLED
    assert report.results[0].error_code == "rate_limited"


def test_failed_calls_are_not_charged(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    adapter = MeteredAdapter(
        errors=[ProviderError(ProviderErrorCategory.AUTHENTICATION_FAILED, "no")]
    )
    config = make_config(max_spend_usd=1.0, max_concurrency=1)
    report = _run(config, make_dataset(count=1), {"m1": adapter})
    assert report.spend is not None
    assert report.spend.estimated_usd == 0


def test_unpriced_billed_models_are_listed(make_config: Callable[..., EvalConfig]) -> None:
    config = make_config(
        models=[{"name": "m1", "provider": "openai_compatible", "model_id": "local"}]
    )
    paid = SemanticSimilarity({"embedding": {"provider": "openai", "model_id": "embed"}})
    free = SemanticSimilarity({"embedding": {"provider": "fake", "model_id": "embed"}})
    assert unpriced_models(config.models, [paid]) == [
        "openai/embed",
        "openai_compatible/local",
    ]
    assert unpriced_models(config.models, [free]) == ["openai_compatible/local"]


def test_free_fake_embeddings_do_not_stop_a_run(
    make_dataset: Callable[..., Dataset], make_config: Callable[..., EvalConfig]
) -> None:
    metric = SemanticSimilarity({"embedding": {"provider": "fake", "model_id": "embed"}})
    config = make_config(max_spend_usd=1.0, max_concurrency=1)
    report = _run(config, make_dataset(count=2), {"m1": MeteredAdapter()}, [metric])
    assert report.status == RunStatus.COMPLETED


@pytest.mark.parametrize("limit", [0, -1])
def test_limit_must_be_positive(make_config: Callable[..., EvalConfig], limit: float) -> None:
    with pytest.raises(ValueError, match="max_spend_usd"):
        make_config(max_spend_usd=limit)


DATASET = {
    "schema_version": "1.0",
    "name": "ds",
    "cases": [
        {"case_key": f"c{i}", "input": {"q": "one two three"}, "expected_output": "x"}
        for i in range(4)
    ],
}


def _write_config(tmp_path: Path, name: str = "eval.yaml", **overrides: Any) -> Path:
    (tmp_path / "ds.json").write_text(json.dumps(DATASET), encoding="utf-8")
    config: dict[str, Any] = {
        "project": "p",
        "dataset": "ds.json",
        "models": [{"name": "m1", "provider": "fake", "model_id": "f"}],
        "metrics": [{"name": "exact_match"}],
        "run": {"max_concurrency": 1, "retry_backoff_seconds": 0},
    }
    config.update(overrides)
    path = tmp_path / name
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def test_config_with_unpriced_model_is_rejected_before_any_call(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        models=[{"name": "m1", "provider": "openai_compatible", "model_id": "local"}],
        run={"max_spend_usd": 1.0},
    )
    with pytest.raises(InputValidationError) as info:
        load_config(path)
    assert "no price for openai_compatible/local" in info.value.format()


def test_custom_pricing_makes_a_model_enforceable(tmp_path: Path) -> None:
    pricing = {
        "pricing_version": "custom",
        "entries": [
            {
                "provider": "openai_compatible",
                "model_id": "local",
                "input_per_million": 1,
                "output_per_million": 1,
                "effective_from": "2026-01-01",
                "source": "test",
            }
        ],
    }
    path = _write_config(
        tmp_path,
        models=[{"name": "m1", "provider": "openai_compatible", "model_id": "local"}],
        metrics=[{"name": "estimated_cost", "config": {"pricing": pricing}}],
        run={"max_spend_usd": 1.0},
    )
    assert load_config(path).config.run.max_spend_usd == 1.0


def test_cli_stopped_run_fails_but_writes_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # A gate that would pass, and a baseline the partial run could not be compared with.
    gates = tmp_path / "gates.yaml"
    gates.write_text(
        yaml.safe_dump(
            {
                "name": "g",
                "rules": [
                    {
                        "metric": "exact_match",
                        "aggregation": "mean",
                        "operator": "gte",
                        "threshold": 0.0,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    baseline = tmp_path / "baseline.json"
    unlimited = _write_config(tmp_path, "unlimited.yaml")
    assert main(["run", "--config", str(unlimited), "--output", str(baseline)]) == EXIT_OK

    limited = _write_config(
        tmp_path,
        "limited.yaml",
        run={"max_concurrency": 1, "retry_backoff_seconds": 0, "max_spend_usd": 0.000001},
    )
    output = tmp_path / "out.json"
    markdown = tmp_path / "out.md"
    capsys.readouterr()
    code = main(
        [
            "run",
            "--config",
            str(limited),
            "--baseline",
            str(baseline),
            "--gates",
            str(gates),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ]
    )

    assert code == EXIT_RUN_FAILED
    assert "Run stopped early" in capsys.readouterr().err
    report = RunReport.model_validate_json(output.read_text(encoding="utf-8"))
    assert report.status == RunStatus.CANCELLED
    assert len(report.results) == 1
    assert report.gate is None
    assert report.comparison is None
    assert report.spend is not None
    assert "Estimated spend" in markdown.read_text(encoding="utf-8")
