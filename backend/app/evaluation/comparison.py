"""Compare a candidate run with a baseline run.

Cases are aligned by ``case_key`` and models by name (or explicit pairs). Only
metrics present in both runs with the same version *and* configuration are
compared: a different judge model or pricing table changes what a score means.
Aggregates are recomputed over the aligned cases only, so a dataset that
gained or lost cases does not shift the averages being compared.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.domain.comparison import (
    CaseChange,
    CaseState,
    ComparisonSettings,
    MetricDelta,
    ModelComparison,
    ModelPair,
    RunComparison,
    RunRef,
    ScoreChange,
    Verdict,
)
from app.domain.metrics import MetricCategory, MetricDirection, MetricInfo, MetricStatus
from app.domain.runs import CaseResult, CaseStatus, RunReport, RunStatus
from app.evaluation.aggregation import MetricShape, summarize_metric

QUALITY_CATEGORIES = frozenset({MetricCategory.ANSWER_QUALITY, MetricCategory.RETRIEVAL_QUALITY})
# Extra aggregations compared for specific metrics, besides the mean.
_EXTRA_AGGREGATIONS: dict[str, tuple[str, ...]] = {"latency": ("p95",)}


class ComparisonError(ValueError):
    """The two runs cannot be compared as requested (e.g. an unknown model in a pair)."""


def metric_shape(info: MetricInfo) -> MetricShape:
    from app.evaluation.registry import METRICS  # registry imports every metric module

    cls = METRICS.get(info.name)
    return MetricShape(info.name, info.version, cls.aggregate_total if cls else False)


def is_quality(info: MetricInfo) -> bool:
    low, high = info.score_range
    return (
        info.category in QUALITY_CATEGORIES and low is not None and high is not None and high > low
    )


def case_state(
    result: CaseResult | None,
    quality: Mapping[str, MetricInfo],
    pass_threshold: float,
) -> tuple[CaseState, list[str]]:
    """Classify one case result. Errors fail; scored quality metrics must all pass."""
    if result is None:
        return CaseState.MISSING, []
    if result.status == CaseStatus.ERROR:
        return CaseState.FAIL, [f"error: {result.error_code or 'unknown_error'}"]
    reasons: list[str] = []
    scored = False
    for metric in result.metrics:
        info = quality.get(metric.metric_name)
        if info is None or metric.status != MetricStatus.SCORED or metric.score is None:
            continue
        scored = True
        low, high = info.score_range
        assert low is not None and high is not None
        normalized = (metric.score - low) / (high - low)
        if info.direction == MetricDirection.LOWER_IS_BETTER:
            normalized = 1 - normalized
        if normalized < pass_threshold:
            reasons.append(f"{metric.metric_name}={metric.score:g} below pass threshold")
    if reasons:
        return CaseState.FAIL, reasons
    return (CaseState.PASS if scored else CaseState.UNKNOWN), []


def _verdict(
    direction: MetricDirection, delta: float | None, tolerance: float
) -> tuple[Verdict, str | None]:
    if delta is None:
        return Verdict.NOT_COMPARABLE, "no scored cases in one of the runs"
    improvement = delta if direction == MetricDirection.HIGHER_IS_BETTER else -delta
    if improvement > tolerance:
        return Verdict.IMPROVED, None
    if improvement < -tolerance:
        return Verdict.REGRESSED, None
    return Verdict.UNCHANGED, None


def _delta(
    metric: str,
    aggregation: str,
    category: MetricCategory | None,
    direction: MetricDirection,
    baseline: float | None,
    candidate: float | None,
    tolerance: float,
) -> MetricDelta:
    delta = candidate - baseline if baseline is not None and candidate is not None else None
    verdict, reason = _verdict(direction, delta, tolerance)
    relative = delta / abs(baseline) if delta is not None and baseline else None
    return MetricDelta(
        metric=metric,
        aggregation=aggregation,
        category=category,
        direction=direction,
        baseline=baseline,
        candidate=candidate,
        delta=delta,
        relative_delta=relative,
        verdict=verdict,
        reason=reason,
    )


def _error_rate(results: Sequence[CaseResult]) -> float | None:
    if not results:
        return None
    return sum(r.status == CaseStatus.ERROR for r in results) / len(results)


def _ref(report: RunReport) -> RunRef:
    return RunRef(
        run_id=report.run_id,
        project=report.project,
        dataset_name=report.dataset.name,
        dataset_hash=report.dataset.content_hash,
        config_hash=report.config_hash,
        finished_at=report.finished_at.isoformat(),
    )


def comparable_metrics(
    baseline: RunReport, candidate: RunReport
) -> tuple[list[MetricInfo], dict[str, str]]:
    """Metrics both runs computed identically, and the reason each other metric is excluded."""
    base = {m.name: m for m in baseline.metrics}
    comparable: list[MetricInfo] = []
    excluded: dict[str, str] = {}
    for info in candidate.metrics:
        other = base.get(info.name)
        if other is None:
            excluded[info.name] = "not computed in the baseline run"
        elif other.version != info.version:
            excluded[info.name] = f"version differs (baseline {other.version}, now {info.version})"
        elif other.config != info.config:
            excluded[info.name] = "configuration differs (e.g. judge model or pricing table)"
        else:
            comparable.append(info)
    for name in base:
        if name not in {m.name for m in candidate.metrics}:
            excluded[name] = "not computed in the candidate run"
    return comparable, excluded


def _pairs(
    baseline: RunReport, candidate: RunReport, settings: ComparisonSettings
) -> tuple[list[ModelPair], list[str]]:
    base_names = [s.model_name for s in baseline.summaries]
    cand_names = [s.model_name for s in candidate.summaries]
    warnings: list[str] = []
    if settings.model_pairs is not None:
        for pair in settings.model_pairs:
            if pair.baseline not in base_names:
                raise ComparisonError(f"model '{pair.baseline}' is not in the baseline run")
            if pair.candidate not in cand_names:
                raise ComparisonError(f"model '{pair.candidate}' is not in the candidate run")
        return list(settings.model_pairs), warnings
    pairs = [ModelPair(baseline=n, candidate=n) for n in cand_names if n in base_names]
    unmatched = [n for n in cand_names if n not in base_names]
    unmatched += [n for n in base_names if n not in cand_names]
    if unmatched:
        warnings.append(
            "models without a same-named counterpart were not compared: "
            + ", ".join(sorted(set(unmatched)))
            + " (use model_pairs to pair differently named models)"
        )
    if not pairs:
        raise ComparisonError("the runs have no model names in common; pass model_pairs")
    return pairs, warnings


def compare_runs(
    baseline: RunReport,
    candidate: RunReport,
    settings: ComparisonSettings | None = None,
) -> RunComparison:
    settings = settings or ComparisonSettings()
    comparable, excluded = comparable_metrics(baseline, candidate)
    pairs, warnings = _pairs(baseline, candidate, settings)
    same_dataset = baseline.dataset.content_hash == candidate.dataset.content_hash
    if not same_dataset:
        warnings.append(
            "the runs used different dataset content; only cases with the same case_key are "
            "compared, and a case's input or reference may have changed between them"
        )
    for label, report in (("baseline", baseline), ("candidate", candidate)):
        if report.status != RunStatus.COMPLETED:
            warnings.append(f"the {label} run is {report.status}; its results are partial")

    models = [_compare_model(baseline, candidate, pair, comparable, settings) for pair in pairs]
    return RunComparison(
        baseline=_ref(baseline),
        candidate=_ref(candidate),
        settings=settings,
        same_dataset=same_dataset,
        excluded_metrics=excluded,
        warnings=warnings,
        models=models,
    )


def _compare_model(
    baseline: RunReport,
    candidate: RunReport,
    pair: ModelPair,
    comparable: Sequence[MetricInfo],
    settings: ComparisonSettings,
) -> ModelComparison:
    base = {r.case_key: r for r in baseline.results if r.model_name == pair.baseline}
    cand = {r.case_key: r for r in candidate.results if r.model_name == pair.candidate}
    keys = [key for key in cand if key in base]
    base_aligned = [base[k] for k in keys]
    cand_aligned = [cand[k] for k in keys]
    tolerance = settings.tolerance

    deltas: list[MetricDelta] = []
    for info in comparable:
        shape = metric_shape(info)
        before = summarize_metric(shape, base_aligned)
        after = summarize_metric(shape, cand_aligned)
        aggregations = ["mean", *_EXTRA_AGGREGATIONS.get(info.name, ())]
        if shape.aggregate_total:
            aggregations.append("total")
        for aggregation in aggregations:
            deltas.append(
                _delta(
                    info.name,
                    aggregation,
                    info.category,
                    info.direction,
                    getattr(before, aggregation),
                    getattr(after, aggregation),
                    tolerance,
                )
            )

    quality = {m.name: m for m in comparable if is_quality(m)}
    newly_failing: list[CaseChange] = []
    recovered: list[CaseChange] = []
    score_changes: list[tuple[float, ScoreChange]] = []
    for key in keys:
        before_state, before_reasons = case_state(base[key], quality, settings.pass_threshold)
        after_state, after_reasons = case_state(cand[key], quality, settings.pass_threshold)
        change = CaseChange(
            case_key=key,
            baseline_state=before_state,
            candidate_state=after_state,
            baseline_reasons=before_reasons,
            candidate_reasons=after_reasons,
        )
        if after_state == CaseState.FAIL and before_state != CaseState.FAIL:
            newly_failing.append(change)
        elif before_state == CaseState.FAIL and after_state == CaseState.PASS:
            recovered.append(change)
        score_changes += _score_changes(key, base[key], cand[key], quality, tolerance)

    score_changes.sort(key=lambda item: (item[0], item[1].case_key, item[1].metric))
    return ModelComparison(
        baseline_model=pair.baseline,
        candidate_model=pair.candidate,
        cases_compared=len(keys),
        cases_only_in_baseline=[k for k in base if k not in cand],
        cases_only_in_candidate=[k for k in cand if k not in base],
        error_rate=_delta(
            "error_rate",
            "overall",
            None,
            MetricDirection.LOWER_IS_BETTER,
            _error_rate(base_aligned),
            _error_rate(cand_aligned),
            tolerance,
        ),
        metrics=deltas,
        newly_failing=newly_failing,
        recovered=recovered,
        score_changes=[change for _, change in score_changes],
    )


def _score_changes(
    key: str,
    before: CaseResult,
    after: CaseResult,
    quality: Mapping[str, MetricInfo],
    tolerance: float,
) -> list[tuple[float, ScoreChange]]:
    """Per-metric score changes for one case, keyed by improvement (negative = regression)."""
    before_scores = _scores(before)
    changes: list[tuple[float, ScoreChange]] = []
    for name, score in _scores(after).items():
        info = quality.get(name)
        old = before_scores.get(name)
        if info is None or old is None:
            continue
        delta = score - old
        improvement = delta if info.direction == MetricDirection.HIGHER_IS_BETTER else -delta
        if abs(improvement) <= tolerance:
            continue
        verdict = "improved" if improvement > 0 else "regressed"
        changes.append(
            (
                improvement,
                ScoreChange(
                    case_key=key,
                    metric=name,
                    baseline=old,
                    candidate=score,
                    delta=delta,
                    verdict=verdict,
                ),
            )
        )
    return changes


def _scores(result: CaseResult) -> dict[str, float]:
    return {
        m.metric_name: m.score
        for m in result.metrics
        if m.status == MetricStatus.SCORED and m.score is not None
    }
