"""Aggregate per-case results into per-model summaries."""

from __future__ import annotations

import math
import statistics
from collections import Counter
from collections.abc import Sequence

from app.domain.metrics import MetricStatus
from app.domain.models import ModelConfigSnapshot
from app.domain.runs import CaseResult, CaseStatus, MetricSummary, ModelSummary, UsageSummary
from app.evaluation.metrics.base import Metric

# Below this many observations, percentile statistics are flagged as small-sample.
SMALL_SAMPLE_THRESHOLD = 20


def percentile(values: Sequence[float], q: float) -> float:
    """Nearest-rank percentile: the smallest value with at least ``q``% of values <= it."""
    if not values:
        raise ValueError("percentile of empty sequence")
    if not 0 < q <= 100:
        raise ValueError("q must be in (0, 100]")
    ordered = sorted(values)
    rank = math.ceil(q / 100 * len(ordered))
    return ordered[rank - 1]


def summarize_metric(metric: Metric, results: Sequence[CaseResult]) -> MetricSummary:
    scores: list[float] = []
    not_applicable = errors = 0
    for case in results:
        for result in case.metrics:
            if result.metric_name != metric.name:
                continue
            if result.status == MetricStatus.SCORED and result.score is not None:
                scores.append(result.score)
            elif result.status == MetricStatus.NOT_APPLICABLE:
                not_applicable += 1
            else:
                errors += 1

    summary = MetricSummary(
        metric_version=metric.version,
        scored_count=len(scores),
        not_applicable_count=not_applicable,
        error_count=errors,
        small_sample=len(scores) < SMALL_SAMPLE_THRESHOLD,
    )
    if not scores:
        return summary
    return summary.model_copy(
        update={
            "mean": statistics.fmean(scores),
            "median": statistics.median(scores),
            "p95": percentile(scores, 95),
            "min": min(scores),
            "max": max(scores),
        }
    )


def summarize_model(
    model: ModelConfigSnapshot, results: Sequence[CaseResult], metrics: Sequence[Metric]
) -> ModelSummary:
    errors = [r for r in results if r.status == CaseStatus.ERROR]
    with_usage = [r for r in results if r.input_tokens is not None or r.output_tokens is not None]
    return ModelSummary(
        model_name=model.name,
        provider=model.provider,
        model_id=model.model_id,
        case_count=len(results),
        success_count=len(results) - len(errors),
        error_count=len(errors),
        error_rate=len(errors) / len(results) if results else 0.0,
        error_codes=dict(Counter(r.error_code or "unknown_error" for r in errors)),
        usage=UsageSummary(
            cases_with_usage=len(with_usage),
            input_tokens_total=sum(r.input_tokens or 0 for r in with_usage),
            output_tokens_total=sum(r.output_tokens or 0 for r in with_usage),
        ),
        metrics={metric.name: summarize_metric(metric, results) for metric in metrics},
    )
