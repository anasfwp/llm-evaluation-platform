"""Evaluation run configuration, per-case results, summaries, and the run report."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.gates import GateResult
from app.domain.metrics import MetricInfo, MetricResult
from app.domain.models import ModelConfigSnapshot

REPORT_SCHEMA_VERSION = "1.0"


class MetricSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    # When set, must match the implemented version so scores are never silently reinterpreted.
    version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class RunSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_seconds: float = Field(default=60, gt=0, le=600)
    max_concurrency: int = Field(default=4, ge=1, le=64)
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.5, ge=0, le=30)
    max_cases: int = Field(default=1000, ge=1, le=100_000)


class ReportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    json_path: str | None = Field(default=None, alias="json")
    markdown_path: str | None = Field(default=None, alias="markdown")


class EvalConfig(BaseModel):
    """Evaluation configuration file (YAML). Relative paths resolve against the file's folder."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: Literal["1.0"] = "1.0"
    project: str = Field(min_length=1, max_length=200)
    dataset: str = Field(min_length=1)
    models: list[ModelConfigSnapshot] = Field(min_length=1)
    metrics: list[MetricSelection] = Field(min_length=1)
    run: RunSettings = Field(default_factory=RunSettings)
    report: ReportSettings = Field(default_factory=ReportSettings)
    gates: str | None = None

    @model_validator(mode="after")
    def _names_unique(self) -> EvalConfig:
        for label, names in (
            ("model name", [m.name for m in self.models]),
            ("metric", [m.name for m in self.metrics]),
        ):
            duplicates = sorted({n for n in names if names.count(n) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label}: {', '.join(duplicates)}")
        return self

    def config_hash(self) -> str:
        canonical = json.dumps(
            self.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":")
        )
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CaseStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"


class CaseResult(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    case_key: str
    model_name: str
    provider: str
    model_id: str
    status: CaseStatus
    tags: list[str] = Field(default_factory=list)
    input: dict[str, Any]
    expected_output: str | None
    actual_output: str | None
    latency_ms: float | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    attempts: int
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime
    metrics: list[MetricResult] = Field(default_factory=list)


class MetricSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_version: str
    scored_count: int
    not_applicable_count: int
    error_count: int
    mean: float | None = None
    median: float | None = None
    p95: float | None = None
    min: float | None = None
    max: float | None = None
    # Percentiles over few observations are unstable; flagged rather than hidden.
    small_sample: bool


class UsageSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    cases_with_usage: int
    input_tokens_total: int
    output_tokens_total: int


class ModelSummary(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    model_name: str
    provider: str
    model_id: str
    case_count: int
    success_count: int
    error_count: int
    error_rate: float
    error_codes: dict[str, int]
    usage: UsageSummary
    metrics: dict[str, MetricSummary]

    @property
    def all_failed(self) -> bool:
        return self.case_count > 0 and self.success_count == 0


class DatasetInfo(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    schema_version: str
    content_hash: str
    case_count: int
    source: str


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_schema_version: str = REPORT_SCHEMA_VERSION
    run_id: str
    project: str
    status: RunStatus
    software_version: str
    started_at: datetime
    finished_at: datetime
    dataset: DatasetInfo
    config_hash: str
    config_snapshot: dict[str, Any]
    metrics: list[MetricInfo]
    summaries: list[ModelSummary]
    results: list[CaseResult]
    gate: GateResult | None = None
