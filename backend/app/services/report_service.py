"""Rebuild a ``RunReport`` from persisted rows so the API exports exactly what the CLI writes."""

from __future__ import annotations

from typing import Literal

from sqlalchemy.orm import Session

from app.core.errors import ConflictError
from app.db.models import EvaluationRun
from app.db.repositories import datasets as dataset_repo
from app.db.repositories import runs as repo
from app.domain.metrics import MetricInfo
from app.domain.runs import (
    CaseResult,
    DatasetInfo,
    EvalConfig,
    ModelSummary,
    RunReport,
    RunStatus,
)
from app.evaluation.aggregation import summarize_model
from app.evaluation.registry import build_metric
from app.evaluation.reporting import render_csv, render_markdown
from app.utils.time import utc_now

ReportFormat = Literal["json", "csv", "markdown"]
_TERMINAL = {RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED}


def _ordered_results(session: Session, run: EvaluationRun, config: EvalConfig) -> list[CaseResult]:
    rows, _ = repo.list_results(session, run.id)
    model_order = {model.name: index for index, model in enumerate(config.models)}
    rows.sort(key=lambda row: (model_order.get(row.model_name, len(model_order)), row.position))
    return [repo.to_domain_result(row) for row in rows]


def summarize_persisted(session: Session, run: EvaluationRun) -> list[ModelSummary]:
    config = EvalConfig.model_validate(run.config_snapshot_json)
    metrics = [build_metric(s.name, s.version, s.config) for s in config.metrics]
    results = _ordered_results(session, run, config)
    return [
        summarize_model(model, [r for r in results if r.model_name == model.name], metrics)
        for model in config.models
    ]


def build_report(session: Session, run: EvaluationRun) -> RunReport:
    if run.status not in _TERMINAL:
        raise ConflictError(f"the report is available once the run finishes (status: {run.status})")
    config = EvalConfig.model_validate(run.config_snapshot_json)
    version = dataset_repo.get_version_by_id(session, run.dataset_version_id)
    dataset = dataset_repo.get(session, version.dataset_id) if version is not None else None
    if version is None or dataset is None:
        raise ConflictError("the dataset version for this run no longer exists")
    return RunReport(
        run_id=str(run.id),
        project=config.project,
        status=RunStatus(run.status),
        software_version=run.software_version,
        started_at=run.started_at or run.created_at,
        finished_at=run.finished_at or utc_now(),
        dataset=DatasetInfo(
            name=dataset.name,
            schema_version=version.schema_version,
            content_hash=version.content_hash,
            case_count=version.case_count,
            source=config.dataset,
        ),
        config_hash=run.config_hash,
        config_snapshot=run.config_snapshot_json,
        metrics=[MetricInfo.model_validate(info) for info in run.metric_infos_json],
        summaries=[ModelSummary.model_validate(s) for s in run.summary_json or []],
        results=_ordered_results(session, run, config),
    )


def render_report(report: RunReport, fmt: ReportFormat) -> tuple[str, str, str]:
    """Return ``(content, media_type, filename)``."""
    stem = f"run-{report.run_id}"
    if fmt == "csv":
        return render_csv(report), "text/csv", f"{stem}.csv"
    if fmt == "markdown":
        return render_markdown(report), "text/markdown", f"{stem}.md"
    return report.model_dump_json(indent=2) + "\n", "application/json", f"{stem}.json"
