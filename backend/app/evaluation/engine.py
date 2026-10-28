"""Evaluation engine: runs every case against every model with bounded concurrency,
timeouts, and bounded retries, then scores and aggregates the results.

The engine has no knowledge of the CLI, HTTP, or storage; callers hand it a
``RunPlan`` and receive a ``RunReport``. Callers that persist results
incrementally pass ``on_result``; callers that support cancellation pass
``is_cancelled``, which is checked before each case starts.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from app import __version__
from app.domain.datasets import Dataset, EvaluationCase
from app.domain.metrics import MetricResult, MetricStatus
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.domain.runs import CaseResult, CaseStatus, DatasetInfo, EvalConfig, RunReport, RunStatus
from app.evaluation.aggregation import summarize_model
from app.evaluation.metrics.base import Metric, MetricInput
from app.providers.base import ModelAdapter, ProviderError
from app.utils.redaction import safe_error_message
from app.utils.time import utc_now

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunPlan:
    config: EvalConfig
    dataset: Dataset
    dataset_source: str
    metrics: Sequence[Metric]
    # Keyed by model config name.
    adapters: Mapping[str, ModelAdapter]


@dataclass(frozen=True)
class _Hooks:
    on_result: Callable[[CaseResult], None] | None
    is_cancelled: Callable[[], bool] | None


async def run_evaluation(
    plan: RunPlan,
    *,
    run_id: str | None = None,
    on_result: Callable[[CaseResult], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> RunReport:
    started_at = utc_now()
    cases = plan.dataset.cases
    hooks = _Hooks(on_result=on_result, is_cancelled=is_cancelled)

    per_model: list[list[CaseResult]] = []
    cancelled = False
    try:
        for model in plan.config.models:
            limit = asyncio.Semaphore(model.max_concurrency or plan.config.run.max_concurrency)
            adapter = plan.adapters[model.name]
            tasks = [_evaluate_case(plan, adapter, model, case, limit, hooks) for case in cases]
            try:
                # gather preserves order, so results follow dataset order.
                outcomes = await asyncio.gather(*tasks)
            finally:
                await _close(adapter)
            cancelled = cancelled or any(outcome is None for outcome in outcomes)
            per_model.append([outcome for outcome in outcomes if outcome is not None])
    finally:
        for metric in plan.metrics:
            await _close(metric)

    summaries = [
        summarize_model(model, results, plan.metrics)
        for model, results in zip(plan.config.models, per_model, strict=True)
    ]
    return RunReport(
        run_id=run_id or str(uuid.uuid4()),
        project=plan.config.project,
        status=RunStatus.CANCELLED if cancelled else RunStatus.COMPLETED,
        software_version=__version__,
        started_at=started_at,
        finished_at=utc_now(),
        dataset=DatasetInfo(
            name=plan.dataset.name,
            schema_version=plan.dataset.schema_version,
            content_hash=plan.dataset.content_hash(),
            case_count=len(cases),
            source=plan.dataset_source,
        ),
        config_hash=plan.config.config_hash(),
        config_snapshot=plan.config.model_dump(mode="json", by_alias=True),
        metrics=[metric.info() for metric in plan.metrics],
        summaries=summaries,
        results=[result for results in per_model for result in results],
    )


async def _evaluate_case(
    plan: RunPlan,
    adapter: ModelAdapter,
    model: ModelConfigSnapshot,
    case: EvaluationCase,
    limit: asyncio.Semaphore,
    hooks: _Hooks,
) -> CaseResult | None:
    """Return the case result, or ``None`` if the run was cancelled before it started."""
    async with limit:
        if hooks.is_cancelled is not None and hooks.is_cancelled():
            return None
        started_at = utc_now()
        response, latency_ms, attempts, error = await _call_with_retries(plan, adapter, model, case)
        finished_at = utc_now()

    if response is not None:
        metric_input = MetricInput(case=case, response=response, latency_ms=latency_ms)
        metric_results = [await _score(metric, metric_input) for metric in plan.metrics]
    else:
        # No output to score: metrics are not applicable, and the failure is counted
        # in the model's error_rate instead of being folded into quality scores.
        metric_results = [
            metric.not_applicable("model call failed; see case error") for metric in plan.metrics
        ]

    result = CaseResult(
        case_key=case.case_key,
        model_name=model.name,
        provider=model.provider,
        model_id=model.model_id,
        status=CaseStatus.SUCCESS if response is not None else CaseStatus.ERROR,
        tags=case.tags,
        input=case.input,
        expected_output=case.expected_output,
        actual_output=response.output_text if response is not None else None,
        latency_ms=round(latency_ms, 3) if latency_ms is not None else None,
        input_tokens=response.input_tokens if response is not None else None,
        output_tokens=response.output_tokens if response is not None else None,
        attempts=attempts,
        error_code=str(error.category) if error is not None else None,
        error_message=safe_error_message(error.message) if error is not None else None,
        started_at=started_at,
        finished_at=finished_at,
        metrics=metric_results,
    )
    if hooks.on_result is not None:
        hooks.on_result(result)
    return result


async def _call_with_retries(
    plan: RunPlan,
    adapter: ModelAdapter,
    model: ModelConfigSnapshot,
    case: EvaluationCase,
) -> tuple[NormalizedModelResponse | None, float | None, int, ProviderError | None]:
    """Return ``(response, latency_ms, attempts, error)``. Only transient errors are retried."""
    settings = plan.config.run
    timeout = model.timeout_seconds or settings.timeout_seconds
    request = ModelRequest(case_key=case.case_key, input_data=case.input)
    error: ProviderError | None = None
    latency_ms: float | None = None

    for attempt in range(1, settings.max_retries + 2):
        start = time.perf_counter()
        try:
            response = await asyncio.wait_for(
                adapter.generate(request=request, model_config=model, timeout_seconds=timeout),
                timeout=timeout,
            )
            return response, (time.perf_counter() - start) * 1000, attempt, None
        except TimeoutError:
            error = ProviderError(ProviderErrorCategory.TIMEOUT, f"no response within {timeout}s")
        except ProviderError as exc:
            error = exc
        except Exception as exc:  # adapter bug: record it, never abort the whole run
            error = ProviderError(ProviderErrorCategory.UNKNOWN, f"{type(exc).__name__}: {exc}")
        latency_ms = (time.perf_counter() - start) * 1000

        if not error.category.is_transient or attempt > settings.max_retries:
            return None, latency_ms, attempt, error
        backoff = settings.retry_backoff_seconds * 2 ** (attempt - 1)
        # Honour a server-requested wait (already capped by the adapter) when it is longer.
        await asyncio.sleep(max(backoff, error.retry_after_seconds or 0.0))

    raise AssertionError("unreachable")  # pragma: no cover


async def _close(resource: ModelAdapter | Metric) -> None:
    close = getattr(resource, "aclose", None)
    if close is None:
        return
    try:
        await close()
    except Exception:  # cleanup failures must never change a run's outcome
        logger.warning("could not close %s", type(resource).__name__, exc_info=True)


async def _score(metric: Metric, data: MetricInput) -> MetricResult:
    try:
        return await metric.evaluate_async(data)
    except Exception as exc:  # one broken metric must not lose the case result
        return MetricResult(
            metric_name=metric.name,
            metric_version=metric.version,
            score=None,
            status=MetricStatus.ERROR,
            details={"error": safe_error_message(f"{type(exc).__name__}: {exc}")},
        )
