"""Quality gate rules (absolute thresholds) and their evaluation results."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Run-level metrics computed from case statuses rather than from a metric implementation.
ERROR_RATE = "error_rate"

Aggregation = Literal["mean", "median", "p95", "min", "max", "count", "overall"]
Operator = Literal["gte", "gt", "lte", "lt", "eq"]


class MissingMetricPolicy(StrEnum):
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


class GateRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(min_length=1)
    aggregation: Aggregation
    operator: Operator
    threshold: float
    # Restrict the rule to one model by its configured name; default is every model.
    model: str | None = None
    missing_metric_policy: MissingMetricPolicy | None = None

    @model_validator(mode="after")
    def _aggregation_matches_metric(self) -> GateRule:
        if self.metric == ERROR_RATE and self.aggregation != "overall":
            raise ValueError("error_rate only supports aggregation 'overall'")
        if self.metric != ERROR_RATE and self.aggregation == "overall":
            raise ValueError("aggregation 'overall' is only valid for error_rate")
        return self


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    name: str = "default"
    missing_metric_policy: MissingMetricPolicy = MissingMetricPolicy.FAIL
    rules: list[GateRule] = Field(min_length=1)


class RuleOutcomeStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNED = "warned"


class RuleOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    metric: str
    aggregation: str
    operator: str
    threshold: float
    model: str
    actual: float | None
    status: RuleOutcomeStatus
    reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.status != RuleOutcomeStatus.FAILED


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate_name: str
    passed: bool
    results: list[RuleOutcome]
