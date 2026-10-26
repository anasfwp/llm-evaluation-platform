"""Run lifecycle: validate and snapshot a run request, dispatch it, execute it in the worker.

State transitions (all committed in their own transaction):

    queued -> running -> completed | cancelled | failed
    queued -> cancelled            (cancelled before a worker picked it up)

Case results are committed one at a time as they finish, so a crash or
cancellation never loses results that were already produced.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from app import __version__
from app.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
    Issue,
    NotFoundError,
)
from app.core.logging import run_id_var
from app.db.models import EvaluationRun
from app.db.repositories import datasets as dataset_repo
from app.db.repositories import model_configs as model_repo
from app.db.repositories import runs as repo
from app.domain.runs import CaseResult, CaseStatus, EvalConfig, RunStatus
from app.evaluation.engine import RunPlan, run_evaluation
from app.evaluation.metrics.base import Metric
from app.evaluation.registry import build_metric
from app.providers.registry import get_provider
from app.schemas.run import RunCreate
from app.services.dataset_service import get_dataset
from app.services.model_config_service import to_snapshot
from app.services.project_service import require_active_project
from app.services.report_service import summarize_persisted
from app.utils.redaction import safe_error_message
from app.utils.time import utc_now

if TYPE_CHECKING:
    from app.services.dispatch import RunDispatcher

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED})


def get_run(session: Session, run_id: uuid.UUID) -> EvaluationRun:
    run = repo.get(session, run_id)
    if run is None:
        raise NotFoundError(f"run {run_id} not found")
    return run


def _build_metrics(data: RunCreate) -> list[Metric]:
    metrics: list[Metric] = []
    issues: list[Issue] = []
    for index, selection in enumerate(data.metrics):
        try:
            metrics.append(build_metric(selection.name, selection.version, selection.config))
        except ValueError as exc:  # includes pydantic ValidationError for metric config
            issues.append(Issue(f"metrics[{index}]", str(exc).splitlines()[0]))
    if issues:
        raise InvalidRequestError("invalid metric selection", issues)
    return metrics


def start_run(
    session: Session,
    data: RunCreate,
    dispatcher: RunDispatcher,
    *,
    max_cases: int,
    max_models: int,
) -> EvaluationRun:
    project = require_active_project(session, data.project_id)
    dataset = get_dataset(session, data.dataset_id)
    if dataset.project_id != project.id:
        raise InvalidRequestError(
            "dataset does not belong to this project", [Issue("dataset_id", "not in project")]
        )
    version_number = data.dataset_version or dataset.current_version
    version = dataset_repo.get_version(session, dataset.id, version_number)
    if version is None:
        raise InvalidRequestError(
            f"dataset has no version {version_number}",
            [Issue("dataset_version", "version not found")],
        )
    if version.case_count > max_cases:
        raise InvalidRequestError(
            f"dataset version has {version.case_count} cases; the per-run limit is {max_cases}"
        )

    if len(set(data.model_config_ids)) != len(data.model_config_ids):
        raise InvalidRequestError(
            "duplicate model configuration", [Issue("model_config_ids", "duplicates")]
        )
    if len(data.model_config_ids) > max_models:
        raise InvalidRequestError(f"at most {max_models} models per run")
    models = model_repo.get_many(session, data.model_config_ids)
    found = {m.id for m in models if m.project_id == project.id}
    missing = [
        Issue(f"model_config_ids[{i}]", "not found in this project")
        for i, model_id in enumerate(data.model_config_ids)
        if model_id not in found
    ]
    if missing:
        raise InvalidRequestError("unknown model configuration", missing)

    metrics = _build_metrics(data)
    config = EvalConfig(
        project=project.name,
        dataset=f"{dataset.name}@v{version.version_number}",
        models=[to_snapshot(m) for m in models],
        metrics=data.metrics,
        run=data.run_config,
    )
    run = EvaluationRun(
        project_id=project.id,
        dataset_version_id=version.id,
        status=RunStatus.QUEUED,
        config_snapshot_json=config.model_dump(mode="json", by_alias=True),
        config_hash=config.config_hash(),
        metric_infos_json=[metric.info().model_dump(mode="json") for metric in metrics],
        software_version=__version__,
        total_cases=version.case_count * len(models),
    )
    session.add(run)
    session.commit()
    logger.info("run queued", extra={"run": str(run.id), "total_cases": run.total_cases})

    try:
        dispatcher.dispatch(run.id)
    except Exception as exc:
        logger.exception("could not dispatch run", extra={"run": str(run.id)})
        session.rollback()
        run = get_run(session, run.id)
        if run.status == RunStatus.QUEUED:
            run.status = RunStatus.FAILED
            run.error_message = "could not enqueue the run; is the worker queue reachable?"
            run.finished_at = utc_now()
            session.commit()
        raise DependencyUnavailableError(
            f"run {run.id} could not be queued: {type(exc).__name__}"
        ) from exc
    session.refresh(run)
    return run


def cancel_run(session: Session, run_id: uuid.UUID) -> EvaluationRun:
    run = get_run(session, run_id)
    if run.status in TERMINAL_STATUSES:
        raise ConflictError(f"run is already {run.status}")
    run.cancel_requested = True
    if run.status == RunStatus.QUEUED:
        run.status = RunStatus.CANCELLED
        run.finished_at = utc_now()
        run.summary_json = []
    session.commit()
    return run


def _build_plan(session: Session, run: EvaluationRun) -> tuple[RunPlan, dict[str, int]]:
    config = EvalConfig.model_validate(run.config_snapshot_json)
    version = dataset_repo.get_version_by_id(session, run.dataset_version_id)
    if version is None:
        raise RuntimeError(f"dataset version {run.dataset_version_id} is missing")
    dataset = get_dataset(session, version.dataset_id)
    content = dataset_repo.load_version(session, dataset, version)
    metrics = [build_metric(s.name, s.version, s.config) for s in config.metrics]
    adapters = {
        model.name: get_provider(model.provider).from_config(model, dataset=content)
        for model in config.models
    }
    plan = RunPlan(
        config=config,
        dataset=content,
        dataset_source=config.dataset,
        metrics=metrics,
        adapters=adapters,
    )
    return plan, {case.case_key: i for i, case in enumerate(content.cases)}


def execute_run(session_factory: sessionmaker[Session], run_id: uuid.UUID) -> None:
    """Worker entry point. Safe to call more than once for the same run."""
    token = run_id_var.set(str(run_id))
    try:
        with session_factory() as session:
            _execute(session, run_id)
    finally:
        run_id_var.reset(token)


def _execute(session: Session, run_id: uuid.UUID) -> None:
    # Claim the run atomically so duplicate task deliveries cannot execute it twice.
    claimed = session.execute(
        update(EvaluationRun)
        .where(EvaluationRun.id == run_id, EvaluationRun.status == RunStatus.QUEUED)
        .values(status=RunStatus.RUNNING, started_at=utc_now())
    )
    session.commit()
    if claimed.rowcount != 1:  # type: ignore[attr-defined]
        logger.info("run not in queued state; skipping execution")
        return
    run = get_run(session, run_id)
    logger.info("run started")

    try:
        plan, positions = _build_plan(session, run)

        def on_result(result: CaseResult) -> None:
            repo.add_case_result(session, run.id, positions[result.case_key], result)
            run.completed_cases += 1
            if result.status == CaseStatus.ERROR:
                run.failed_cases += 1
            session.commit()

        def is_cancelled() -> bool:
            return repo.is_cancel_requested(session, run.id)

        report = asyncio.run(
            run_evaluation(plan, run_id=str(run.id), on_result=on_result, is_cancelled=is_cancelled)
        )
        run.summary_json = [summary.model_dump(mode="json") for summary in report.summaries]
        run.status = report.status
        run.finished_at = utc_now()
        session.commit()
        logger.info(
            "run finished",
            extra={"status": run.status, "completed_cases": run.completed_cases},
        )
    except Exception as exc:
        logger.exception("run failed")
        session.rollback()
        run = get_run(session, run_id)
        run.status = RunStatus.FAILED
        run.error_message = safe_error_message(f"{type(exc).__name__}: {exc}")
        run.finished_at = utc_now()
        try:
            # Partial results are kept; summarize whatever was persisted.
            run.summary_json = [
                s.model_dump(mode="json") for s in summarize_persisted(session, run)
            ]
        except Exception:
            logger.exception("could not summarize partial results")
        session.commit()
