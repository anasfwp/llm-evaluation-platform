"""Metric result types shared by metric implementations, aggregation, and reports."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class MetricStatus(StrEnum):
    SCORED = "scored"
    # Inputs required by the metric are missing; never treated as a zero score.
    NOT_APPLICABLE = "not_applicable"
    # The metric itself failed to compute.
    ERROR = "error"


class MetricCategory(StrEnum):
    ANSWER_QUALITY = "answer_quality"
    RETRIEVAL_QUALITY = "retrieval_quality"
    PERFORMANCE = "performance"
    COST = "cost"


class MetricDirection(StrEnum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class MetricResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric_name: str
    metric_version: str
    score: float | None
    status: MetricStatus
    details: dict[str, Any] = Field(default_factory=dict)


class MetricInfo(BaseModel):
    """Descriptive metadata about a metric, recorded in reports and listed by the CLI."""

    model_config = ConfigDict(frozen=True)

    name: str
    version: str
    category: MetricCategory
    direction: MetricDirection
    unit: str | None
    score_range: tuple[float | None, float | None]
    required_inputs: tuple[str, ...]
    description: str
    config: dict[str, Any] = Field(default_factory=dict)
