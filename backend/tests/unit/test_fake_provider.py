from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.datasets import Dataset
from app.domain.models import ModelConfigSnapshot, ModelRequest, ProviderErrorCategory
from app.providers.base import ProviderError
from app.providers.fake import FakeProvider


def _generate(dataset: Dataset, case_key: str, **parameters: Any) -> str:
    model = ModelConfigSnapshot(name="m", provider="fake", model_id="fake-1", parameters=parameters)
    adapter = FakeProvider.from_config(model, dataset=dataset)
    case = next(c for c in dataset.cases if c.case_key == case_key)
    request = ModelRequest(case_key=case_key, input_data=case.input)
    response = asyncio.run(adapter.generate(request=request, model_config=model, timeout_seconds=1))
    return response.output_text


def test_expected_mode_returns_reference_answer(make_dataset: Callable[..., Dataset]) -> None:
    dataset = make_dataset()
    assert _generate(dataset, "case-1") == "answer 1"


def test_other_modes_and_overrides(make_dataset: Callable[..., Dataset]) -> None:
    dataset = make_dataset()
    assert _generate(dataset, "case-0", mode="echo_input") == "question for case-0"
    assert _generate(dataset, "case-0", mode="constant", constant_output="hi") == "hi"
    assert _generate(dataset, "case-0", overrides={"case-0": {"output": "wrong"}}) == "wrong"


def test_override_error_raises_categorized_provider_error(
    make_dataset: Callable[..., Dataset],
) -> None:
    with pytest.raises(ProviderError) as info:
        _generate(make_dataset(), "case-0", overrides={"case-0": {"error": "rate_limited"}})
    assert info.value.category == ProviderErrorCategory.RATE_LIMITED


def test_response_is_deterministic_and_reports_approximate_usage(
    make_dataset: Callable[..., Dataset],
) -> None:
    dataset = make_dataset()
    model = ModelConfigSnapshot(name="m", provider="fake", model_id="fake-1")
    adapter = FakeProvider.from_config(model, dataset=dataset)
    request = ModelRequest(case_key="case-2", input_data={"question": "one two three"})
    first = asyncio.run(adapter.generate(request=request, model_config=model, timeout_seconds=1))
    second = asyncio.run(adapter.generate(request=request, model_config=model, timeout_seconds=1))
    assert first == second
    assert first.input_tokens == 3
    assert first.output_tokens == 2  # "answer 2"
    assert first.raw_metadata["usage_method"] == "whitespace_approximation"


@pytest.mark.parametrize(
    "parameters",
    [
        {"mode": "random"},
        {"latency_ms": -1},
        {"overrides": {"c": {}}},
        {"overrides": {"c": {"output": "x", "error": "timeout"}}},
        {"overrides": {"c": {"error": "not_a_category"}}},
        {"unknown": True},
    ],
)
def test_invalid_parameters_are_rejected(parameters: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FakeProvider.Parameters.model_validate(parameters)
