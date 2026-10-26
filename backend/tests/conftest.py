from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.domain.datasets import Dataset, EvaluationCase
from app.domain.runs import EvalConfig

CaseFactory = Callable[..., EvaluationCase]
DatasetFactory = Callable[..., Dataset]
ConfigFactory = Callable[..., EvalConfig]


@pytest.fixture
def make_case() -> CaseFactory:
    def factory(
        case_key: str = "case-1", expected: str | None = "Paris", **fields: Any
    ) -> EvaluationCase:
        fields.setdefault("input", {"question": f"question for {case_key}"})
        return EvaluationCase(case_key=case_key, expected_output=expected, **fields)

    return factory


@pytest.fixture
def make_dataset(make_case: CaseFactory) -> DatasetFactory:
    def factory(*cases: EvaluationCase, count: int = 3) -> Dataset:
        chosen = list(cases) or [make_case(f"case-{i}", f"answer {i}") for i in range(count)]
        return Dataset(schema_version="1.0", name="test-dataset", cases=chosen)

    return factory


@pytest.fixture
def make_config() -> ConfigFactory:
    def factory(
        models: list[dict[str, Any]] | None = None,
        metrics: list[str] | None = None,
        **run: Any,
    ) -> EvalConfig:
        run.setdefault("retry_backoff_seconds", 0)
        return EvalConfig.model_validate(
            {
                "project": "test-project",
                "dataset": "dataset.json",
                "models": models or [{"name": "m1", "provider": "fake", "model_id": "fake-1"}],
                "metrics": [{"name": name} for name in (metrics or ["exact_match", "latency"])],
                "run": run,
            }
        )

    return factory
