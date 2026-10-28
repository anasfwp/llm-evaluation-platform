from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import Baseline, Comparison, EvaluationGate
from app.domain.comparison import ComparisonSettings, RunComparison
from app.domain.gates import GateConfig, GateRule, MissingMetricPolicy


class _BaselineChoice(BaseModel):
    """Exactly one way to name the baseline: a run ID or a saved baseline's ID."""

    baseline_run_id: uuid.UUID | None = None
    baseline_id: uuid.UUID | None = None


class ComparisonCreate(_BaselineChoice):
    model_config = ConfigDict(extra="forbid")

    candidate_run_id: uuid.UUID
    settings: ComparisonSettings = Field(default_factory=ComparisonSettings)

    @model_validator(mode="after")
    def _one_baseline(self) -> ComparisonCreate:
        if (self.baseline_run_id is None) == (self.baseline_id is None):
            raise ValueError("give exactly one of baseline_run_id or baseline_id")
        return self


class ComparisonRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    baseline_run_id: uuid.UUID
    candidate_run_id: uuid.UUID
    created_at: datetime
    result: RunComparison

    @classmethod
    def from_model(cls, row: Comparison) -> ComparisonRead:
        return cls(
            id=row.id,
            project_id=row.project_id,
            baseline_run_id=row.baseline_run_id,
            candidate_run_id=row.candidate_run_id,
            created_at=row.created_at,
            result=RunComparison.model_validate(row.summary_json),
        )


class ComparisonListItem(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    baseline_run_id: uuid.UUID
    candidate_run_id: uuid.UUID
    created_at: datetime
    regressed: bool
    newly_failing_count: int
    recovered_count: int

    @classmethod
    def from_model(cls, row: Comparison) -> ComparisonListItem:
        summary: dict[str, Any] = row.summary_json
        return cls(
            id=row.id,
            project_id=row.project_id,
            baseline_run_id=row.baseline_run_id,
            candidate_run_id=row.candidate_run_id,
            created_at=row.created_at,
            regressed=bool(summary.get("regressed")),
            newly_failing_count=int(summary.get("newly_failing_count", 0)),
            recovered_count=int(summary.get("recovered_count", 0)),
        )


class BaselineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    run_id: uuid.UUID


class BaselineUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    # Point the baseline at a newer run (e.g. after accepting a release).
    run_id: uuid.UUID | None = None


class BaselineRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    run_id: uuid.UUID
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row: Baseline) -> BaselineRead:
        return cls(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            description=row.description,
            run_id=row.run_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class GateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    missing_metric_policy: MissingMetricPolicy = MissingMetricPolicy.FAIL
    rules: list[GateRule] = Field(min_length=1, max_length=200)

    def to_config(self) -> GateConfig:
        return GateConfig(
            name=self.name, missing_metric_policy=self.missing_metric_policy, rules=self.rules
        )


class GateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    missing_metric_policy: MissingMetricPolicy | None = None
    rules: list[GateRule] | None = Field(default=None, min_length=1, max_length=200)


class GateRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    missing_metric_policy: MissingMetricPolicy
    rules: list[GateRule]
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, row: EvaluationGate) -> GateRead:
        return cls(
            id=row.id,
            project_id=row.project_id,
            name=row.name,
            missing_metric_policy=MissingMetricPolicy(row.missing_metric_policy),
            rules=[GateRule.model_validate(rule) for rule in row.rules_json],
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def to_config(self) -> GateConfig:
        return GateConfig(
            name=self.name, missing_metric_policy=self.missing_metric_policy, rules=self.rules
        )


class GateEvaluate(_BaselineChoice):
    """Evaluate a saved gate (``gate_id``) or inline ``rules`` against a run."""

    model_config = ConfigDict(extra="forbid")

    run_id: uuid.UUID
    gate_id: uuid.UUID | None = None
    name: str = Field(default="inline", min_length=1, max_length=200)
    rules: list[GateRule] | None = Field(default=None, min_length=1, max_length=200)
    missing_metric_policy: MissingMetricPolicy = MissingMetricPolicy.FAIL

    @model_validator(mode="after")
    def _one_source(self) -> GateEvaluate:
        if (self.gate_id is None) == (self.rules is None):
            raise ValueError("give exactly one of gate_id or rules")
        if self.baseline_run_id is not None and self.baseline_id is not None:
            raise ValueError("give at most one of baseline_run_id or baseline_id")
        return self
