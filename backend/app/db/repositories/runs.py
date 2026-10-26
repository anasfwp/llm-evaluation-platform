from __future__ import annotations

import json
import uuid

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import CaseResult, EvaluationRun, MetricResult
from app.domain import runs as domain
from app.domain.metrics import MetricResult as DomainMetricResult
from app.domain.metrics import MetricStatus


def get(session: Session, run_id: uuid.UUID) -> EvaluationRun | None:
    return session.get(EvaluationRun, run_id)


def list_runs(
    session: Session,
    *,
    project_id: uuid.UUID | None,
    status: str | None,
    limit: int,
    offset: int,
) -> tuple[list[EvaluationRun], int]:
    query = select(EvaluationRun)
    if project_id is not None:
        query = query.where(EvaluationRun.project_id == project_id)
    if status is not None:
        query = query.where(EvaluationRun.status == status)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(
        query.order_by(EvaluationRun.created_at.desc(), EvaluationRun.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(items), total


def is_cancel_requested(session: Session, run_id: uuid.UUID) -> bool:
    return bool(
        session.scalar(select(EvaluationRun.cancel_requested).where(EvaluationRun.id == run_id))
    )


def add_case_result(
    session: Session, run_id: uuid.UUID, position: int, result: domain.CaseResult
) -> CaseResult:
    row = CaseResult(
        run_id=run_id,
        case_key=result.case_key,
        position=position,
        model_name=result.model_name,
        provider=result.provider,
        model_id=result.model_id,
        status=result.status,
        tags_json=result.tags,
        input_snapshot_json=result.input,
        expected_output_snapshot=result.expected_output,
        actual_output=result.actual_output,
        latency_ms=result.latency_ms,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        attempts=result.attempts,
        error_code=result.error_code,
        error_message_redacted=result.error_message,
        started_at=result.started_at,
        finished_at=result.finished_at,
        metrics=[
            MetricResult(
                position=index,
                metric_name=metric.metric_name,
                metric_version=metric.metric_version,
                score=metric.score,
                status=metric.status,
                details_json=metric.details,
            )
            for index, metric in enumerate(result.metrics)
        ],
    )
    session.add(row)
    return row


def list_results(
    session: Session,
    run_id: uuid.UUID,
    *,
    model_name: str | None = None,
    status: str | None = None,
    tag: str | None = None,
    metric: str | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[CaseResult], int]:
    query = select(CaseResult).where(CaseResult.run_id == run_id)
    if model_name is not None:
        query = query.where(CaseResult.model_name == model_name)
    if status is not None:
        query = query.where(CaseResult.status == status)
    if tag is not None:
        # Match the JSON-encoded tag so "geo" does not match "geography".
        query = query.where(
            cast(CaseResult.tags_json, String).contains(json.dumps(tag), autoescape=True)
        )
    if metric is not None:
        scored = select(MetricResult.case_result_id).where(
            MetricResult.metric_name == metric, MetricResult.status == MetricStatus.SCORED
        )
        if min_score is not None:
            scored = scored.where(MetricResult.score >= min_score)
        if max_score is not None:
            scored = scored.where(MetricResult.score <= max_score)
        query = query.where(CaseResult.id.in_(scored))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(CaseResult.model_name, CaseResult.position).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query).all()), total


def get_result(session: Session, run_id: uuid.UUID, result_id: uuid.UUID) -> CaseResult | None:
    return session.scalar(
        select(CaseResult).where(CaseResult.run_id == run_id, CaseResult.id == result_id)
    )


def to_domain_result(row: CaseResult) -> domain.CaseResult:
    return domain.CaseResult(
        case_key=row.case_key,
        model_name=row.model_name,
        provider=row.provider,
        model_id=row.model_id,
        status=domain.CaseStatus(row.status),
        tags=row.tags_json,
        input=row.input_snapshot_json,
        expected_output=row.expected_output_snapshot,
        actual_output=row.actual_output,
        latency_ms=row.latency_ms,
        input_tokens=row.input_tokens,
        output_tokens=row.output_tokens,
        attempts=row.attempts,
        error_code=row.error_code,
        error_message=row.error_message_redacted,
        started_at=row.started_at,
        finished_at=row.finished_at,
        metrics=[
            DomainMetricResult(
                metric_name=m.metric_name,
                metric_version=m.metric_version,
                score=m.score,
                status=MetricStatus(m.status),
                details=m.details_json,
            )
            for m in row.metrics
        ],
    )
