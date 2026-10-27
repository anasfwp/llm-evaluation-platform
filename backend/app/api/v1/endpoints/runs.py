from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import DispatcherDep, PaginationDep, SessionDep, SettingsDep
from app.core.errors import NotFoundError
from app.db.models import EvaluationRun
from app.db.repositories import datasets as dataset_repo
from app.db.repositories import runs as run_repo
from app.domain.metrics import MetricInfo
from app.domain.runs import CaseStatus, RunStatus
from app.evaluation.registry import METRICS
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.run import CaseResultRead, RunAccepted, RunCreate, RunDatasetRef, RunRead
from app.services import report_service, run_service
from app.services.report_service import ReportFormat

router = APIRouter(tags=["runs"], responses=ERROR_RESPONSES)


def _read(session: Session, run: EvaluationRun) -> RunRead:
    version = dataset_repo.get_version_by_id(session, run.dataset_version_id)
    dataset = dataset_repo.get(session, version.dataset_id) if version is not None else None
    if version is None or dataset is None:  # pragma: no cover - guarded by foreign keys
        raise NotFoundError(f"dataset version for run {run.id} not found")
    ref = RunDatasetRef(
        id=dataset.id,
        name=dataset.name,
        version=version.version_number,
        content_hash=version.content_hash,
    )
    return RunRead.from_model(run, ref)


@router.get("/metrics")
def list_metrics() -> list[MetricInfo]:
    """Available metrics, their versions, required inputs, and score direction."""
    return [cls.describe() for cls in METRICS.values()]


@router.post("/runs", status_code=status.HTTP_202_ACCEPTED)
def start_run(
    data: RunCreate, session: SessionDep, settings: SettingsDep, dispatcher: DispatcherDep
) -> RunAccepted:
    run = run_service.start_run(
        session,
        data,
        dispatcher,
        max_cases=settings.max_cases_per_run,
        max_models=settings.max_models_per_run,
        allowed_env=settings.provider_env_allowed,
    )
    return RunAccepted(
        run_id=run.id, status=RunStatus(run.status), status_url=f"/api/v1/runs/{run.id}"
    )


@router.get("/runs")
def list_runs(
    session: SessionDep,
    page: PaginationDep,
    project_id: uuid.UUID | None = None,
    status: RunStatus | None = None,
) -> Page[RunRead]:
    items, total = run_repo.list_runs(
        session, project_id=project_id, status=status, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[_read(session, run) for run in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, session: SessionDep) -> RunRead:
    return _read(session, run_service.get_run(session, run_id))


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_run(run_id: uuid.UUID, session: SessionDep) -> RunRead:
    """Queued runs are cancelled immediately; running runs stop before their next case."""
    return _read(session, run_service.cancel_run(session, run_id))


@router.get("/runs/{run_id}/results")
def list_results(
    run_id: uuid.UUID,
    session: SessionDep,
    page: PaginationDep,
    model_name: str | None = None,
    status: CaseStatus | None = None,
    tag: str | None = None,
    metric: Annotated[str | None, Query(description="Only cases scored on this metric")] = None,
    min_score: Annotated[float | None, Query(description="Requires 'metric'")] = None,
    max_score: Annotated[float | None, Query(description="Requires 'metric'")] = None,
) -> Page[CaseResultRead]:
    run_service.get_run(session, run_id)
    rows, total = run_repo.list_results(
        session,
        run_id,
        model_name=model_name,
        status=status,
        tag=tag,
        metric=metric,
        min_score=min_score,
        max_score=max_score,
        limit=page.limit,
        offset=page.offset,
    )
    return Page(
        items=[CaseResultRead.from_model(row) for row in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/runs/{run_id}/results/{result_id}")
def get_result(run_id: uuid.UUID, result_id: uuid.UUID, session: SessionDep) -> CaseResultRead:
    row = run_repo.get_result(session, run_id, result_id)
    if row is None:
        raise NotFoundError(f"result {result_id} not found in run {run_id}")
    return CaseResultRead.from_model(row)


@router.get("/runs/{run_id}/report")
def export_report(
    run_id: uuid.UUID, session: SessionDep, format: ReportFormat = "json"
) -> Response:
    run = run_service.get_run(session, run_id)
    report = report_service.build_report(session, run)
    content, media_type, filename = report_service.render_report(report, format)
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
