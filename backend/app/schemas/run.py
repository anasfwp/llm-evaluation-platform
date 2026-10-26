from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import CaseResult, EvaluationRun
from app.db.repositories.runs import to_domain_result
from app.domain.metrics import MetricResult
from app.domain.runs import MetricSelection, ModelSummary, RunSettings, RunStatus


class RunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    project_id: uuid.UUID
    dataset_id: uuid.UUID
    # Defaults to the dataset's current version; the run always pins an exact version.
    dataset_version: int | None = Field(default=None, ge=1)
    model_config_ids: list[uuid.UUID] = Field(min_length=1)
    metrics: list[MetricSelection] = Field(min_length=1)
    run_config: RunSettings = Field(default_factory=RunSettings)


class RunAccepted(BaseModel):
    run_id: uuid.UUID
    status: RunStatus
    status_url: str


class RunProgress(BaseModel):
    total_cases: int
    completed_cases: int
    failed_cases: int


class RunDatasetRef(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    content_hash: str


class RunRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: RunStatus
    dataset: RunDatasetRef
    progress: RunProgress
    cancel_requested: bool
    # Present once the run reaches a terminal state.
    models: list[ModelSummary] | None
    config_hash: str
    config_snapshot: dict[str, Any]
    software_version: str
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_model(cls, run: EvaluationRun, dataset: RunDatasetRef) -> RunRead:
        return cls(
            id=run.id,
            project_id=run.project_id,
            status=RunStatus(run.status),
            dataset=dataset,
            progress=RunProgress(
                total_cases=run.total_cases,
                completed_cases=run.completed_cases,
                failed_cases=run.failed_cases,
            ),
            cancel_requested=run.cancel_requested,
            models=(
                [ModelSummary.model_validate(s) for s in run.summary_json]
                if run.summary_json is not None
                else None
            ),
            config_hash=run.config_hash,
            config_snapshot=run.config_snapshot_json,
            software_version=run.software_version,
            error_message=run.error_message,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
        )


class CaseResultRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    run_id: uuid.UUID
    case_key: str
    model_name: str
    provider: str
    model_id: str
    status: str
    tags: list[str]
    input: dict[str, Any]
    expected_output: str | None
    actual_output: str | None
    latency_ms: float | None
    input_tokens: int | None
    output_tokens: int | None
    attempts: int
    error_code: str | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime
    metrics: list[MetricResult]

    @classmethod
    def from_model(cls, row: CaseResult) -> CaseResultRead:
        return cls(id=row.id, run_id=row.run_id, **to_domain_result(row).model_dump())
