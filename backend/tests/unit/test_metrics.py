from __future__ import annotations

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.domain.datasets import EvaluationCase
from app.domain.metrics import MetricStatus
from app.domain.models import NormalizedModelResponse
from app.evaluation.metrics.base import MetricInput
from app.evaluation.metrics.exact_match import ExactMatch
from app.evaluation.metrics.latency import Latency
from app.evaluation.registry import build_metric

CaseFactory = Callable[..., EvaluationCase]


def _input(
    make_case: CaseFactory, expected: str | None, actual: str, latency: float | None = 5.0
) -> MetricInput:
    response = NormalizedModelResponse(output_text=actual, provider="fake", model_id="m")
    return MetricInput(case=make_case(expected=expected), response=response, latency_ms=latency)


def test_exact_match_scores_one_after_normalization(make_case: CaseFactory) -> None:
    result = ExactMatch().evaluate(_input(make_case, "Paris", " paris. "))
    assert result.status == MetricStatus.SCORED
    assert result.score == 1.0
    assert result.details["compared_actual"] == "paris"


def test_exact_match_scores_zero_on_mismatch(make_case: CaseFactory) -> None:
    result = ExactMatch().evaluate(_input(make_case, "Canberra", "Sydney"))
    assert result.score == 0.0
    assert result.status == MetricStatus.SCORED


def test_exact_match_without_normalization_is_strict(make_case: CaseFactory) -> None:
    result = ExactMatch({"normalize": False}).evaluate(_input(make_case, "Paris", "paris"))
    assert result.score == 0.0


def test_exact_match_empty_output_is_a_mismatch_not_missing(make_case: CaseFactory) -> None:
    result = ExactMatch().evaluate(_input(make_case, "Paris", ""))
    assert result.status == MetricStatus.SCORED
    assert result.score == 0.0


def test_exact_match_not_applicable_without_expected_output(make_case: CaseFactory) -> None:
    result = ExactMatch().evaluate(_input(make_case, None, "anything"))
    assert result.status == MetricStatus.NOT_APPLICABLE
    assert result.score is None
    assert "expected_output" in result.details["reason"]


def test_exact_match_rejects_unknown_config() -> None:
    with pytest.raises(ValidationError):
        ExactMatch({"normalise": True})


def test_latency_reports_milliseconds(make_case: CaseFactory) -> None:
    result = Latency().evaluate(_input(make_case, "x", "x", latency=12.34567))
    assert result.score == 12.346
    assert Latency.describe().unit == "ms"


def test_latency_not_applicable_when_unmeasured(make_case: CaseFactory) -> None:
    result = Latency().evaluate(_input(make_case, "x", "x", latency=None))
    assert result.status == MetricStatus.NOT_APPLICABLE


def test_registry_rejects_unknown_metric_and_version() -> None:
    with pytest.raises(ValueError, match="unknown metric"):
        build_metric("bleu", None, {})
    with pytest.raises(ValueError, match=r"version '2\.0' is not available"):
        build_metric("exact_match", "2.0", {})
    assert build_metric("exact_match", "1.0", {}).version == "1.0"
