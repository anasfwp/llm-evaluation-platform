from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.domain.metrics import MetricResult, MetricStatus
from app.domain.models import ModelConfigSnapshot
from app.domain.runs import CaseResult, CaseStatus
from app.evaluation.aggregation import percentile, summarize_model
from app.evaluation.metrics.exact_match import ExactMatch

NOW = datetime(2026, 1, 1, tzinfo=UTC)
MODEL = ModelConfigSnapshot(name="m1", provider="fake", model_id="fake-1")


def _result(key: str, score: float | None, *, error: bool = False, tokens: int | None = 3):
    status = MetricStatus.NOT_APPLICABLE if score is None else MetricStatus.SCORED
    return CaseResult(
        case_key=key,
        model_name="m1",
        provider="fake",
        model_id="fake-1",
        status=CaseStatus.ERROR if error else CaseStatus.SUCCESS,
        input={"q": key},
        expected_output="x",
        actual_output=None if error else "x",
        latency_ms=1.0,
        input_tokens=None if error else tokens,
        output_tokens=None if error else tokens,
        attempts=1,
        error_code="timeout" if error else None,
        started_at=NOW,
        finished_at=NOW,
        metrics=[
            MetricResult(
                metric_name="exact_match", metric_version="1.0", score=score, status=status
            )
        ],
    )


@pytest.mark.parametrize(
    ("values", "q", "expected"),
    [
        ([5.0], 95, 5.0),
        ([1.0, 2.0, 3.0, 4.0], 50, 2.0),
        ([float(i) for i in range(1, 101)], 95, 95.0),
        ([float(i) for i in range(1, 21)], 95, 19.0),
        ([3.0, 1.0, 2.0], 100, 3.0),
    ],
)
def test_percentile_nearest_rank(values: list[float], q: float, expected: float) -> None:
    assert percentile(values, q) == expected


def test_percentile_rejects_empty_and_bad_q() -> None:
    with pytest.raises(ValueError):
        percentile([], 95)
    with pytest.raises(ValueError):
        percentile([1.0], 0)


def test_summary_excludes_errors_and_not_applicable_from_scores() -> None:
    results = [
        _result("a", 1.0),
        _result("b", 0.0),
        _result("c", 1.0),
        _result("d", None),
        _result("e", None, error=True),
    ]
    summary = summarize_model(MODEL, results, [ExactMatch()])

    assert summary.case_count == 5
    assert summary.success_count == 4
    assert summary.error_count == 1
    assert summary.error_rate == pytest.approx(0.2)
    assert summary.error_codes == {"timeout": 1}

    em = summary.metrics["exact_match"]
    assert em.scored_count == 3
    assert em.not_applicable_count == 2
    assert em.mean == pytest.approx(2 / 3)
    assert em.small_sample is True


def test_summary_usage_totals_only_count_cases_with_usage() -> None:
    results = [
        _result("a", 1.0, tokens=4),
        _result("b", 1.0, tokens=6),
        _result("c", 1.0, error=True),
    ]
    usage = summarize_model(MODEL, results, [ExactMatch()]).usage
    assert usage.cases_with_usage == 2
    assert usage.input_tokens_total == 10
    assert usage.output_tokens_total == 10


def test_summary_with_no_scores_has_no_statistics() -> None:
    summary = summarize_model(MODEL, [_result("a", None, error=True)], [ExactMatch()])
    em = summary.metrics["exact_match"]
    assert em.scored_count == 0
    assert em.mean is None and em.p95 is None
    assert summary.all_failed is True
