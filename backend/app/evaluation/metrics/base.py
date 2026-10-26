"""Metric contract. A metric owns exactly one documented scoring rule."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from app.domain.datasets import EvaluationCase
from app.domain.metrics import (
    MetricCategory,
    MetricDirection,
    MetricInfo,
    MetricResult,
    MetricStatus,
)
from app.domain.models import NormalizedModelResponse


class NoConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


@dataclass(frozen=True)
class MetricInput:
    """Everything a metric may look at for one successful model call."""

    case: EvaluationCase
    response: NormalizedModelResponse
    latency_ms: float | None


class Metric(ABC):
    name: ClassVar[str]
    version: ClassVar[str]
    category: ClassVar[MetricCategory]
    direction: ClassVar[MetricDirection]
    unit: ClassVar[str | None] = None
    score_range: ClassVar[tuple[float | None, float | None]]
    required_inputs: ClassVar[tuple[str, ...]]
    description: ClassVar[str]
    Config: ClassVar[type[BaseModel]] = NoConfig

    def __init__(self, config: Mapping[str, Any] | None = None) -> None:
        self.config = self.Config.model_validate(dict(config or {}))

    @abstractmethod
    def evaluate(self, data: MetricInput) -> MetricResult: ...

    @classmethod
    def describe(cls) -> MetricInfo:
        return MetricInfo(
            name=cls.name,
            version=cls.version,
            category=cls.category,
            direction=cls.direction,
            unit=cls.unit,
            score_range=cls.score_range,
            required_inputs=cls.required_inputs,
            description=cls.description,
        )

    def info(self) -> MetricInfo:
        return self.describe().model_copy(update={"config": self.config.model_dump(mode="json")})

    def scored(self, score: float, **details: Any) -> MetricResult:
        return MetricResult(
            metric_name=self.name,
            metric_version=self.version,
            score=score,
            status=MetricStatus.SCORED,
            details=details,
        )

    def not_applicable(self, reason: str) -> MetricResult:
        return MetricResult(
            metric_name=self.name,
            metric_version=self.version,
            score=None,
            status=MetricStatus.NOT_APPLICABLE,
            details={"reason": reason},
        )
