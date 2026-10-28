"""Comparison of a candidate run against a baseline run, aligned by stable case key."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.domain.metrics import MetricCategory, MetricDirection

COMPARISON_SCHEMA_VERSION = "1.0"


class ModelPair(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline: str = Field(min_length=1)
    candidate: str = Field(min_length=1)


class ComparisonSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # A quality score passes when (score - min) / (max - min) >= pass_threshold, using the
    # metric's declared range: exact_match needs 1.0, a 1-5 judge score needs >= 3.
    pass_threshold: float = Field(default=0.5, ge=0, le=1)
    # Score and aggregate changes no larger than this are reported as unchanged.
    tolerance: float = Field(default=1e-9, ge=0)
    # Explicit model pairing; by default models are paired by identical name.
    model_pairs: list[ModelPair] | None = Field(default=None, min_length=1, max_length=50)


class CaseState(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    # Answered, but no comparable quality metric was scored (e.g. open-ended cases).
    UNKNOWN = "unknown"
    MISSING = "missing"


class Verdict(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    NOT_COMPARABLE = "not_comparable"


class MetricDelta(BaseModel):
    model_config = ConfigDict(frozen=True)

    metric: str
    aggregation: str
    # None for the run-level error_rate.
    category: MetricCategory | None
    direction: MetricDirection
    baseline: float | None
    candidate: float | None
    delta: float | None
    # delta / |baseline|, None when the baseline is zero or missing.
    relative_delta: float | None
    verdict: Verdict
    reason: str | None = None


class CaseChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_key: str
    baseline_state: CaseState
    candidate_state: CaseState
    baseline_reasons: list[str] = Field(default_factory=list)
    candidate_reasons: list[str] = Field(default_factory=list)


class ScoreChange(BaseModel):
    model_config = ConfigDict(frozen=True)

    case_key: str
    metric: str
    baseline: float
    candidate: float
    delta: float
    verdict: Literal["improved", "regressed"]


class ModelComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    baseline_model: str
    candidate_model: str
    cases_compared: int
    cases_only_in_baseline: list[str]
    cases_only_in_candidate: list[str]
    error_rate: MetricDelta
    metrics: list[MetricDelta]
    newly_failing: list[CaseChange]
    recovered: list[CaseChange]
    # Per-case score changes beyond the tolerance, worst regressions first.
    score_changes: list[ScoreChange]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def regressed(self) -> bool:
        """Newly failing cases, a higher error rate, or a lower quality aggregate.

        Latency and cost changes are reported but do not count: they move on every run.
        Gate on them with relative rules instead.
        """
        quality = (MetricCategory.ANSWER_QUALITY, MetricCategory.RETRIEVAL_QUALITY)
        return (
            bool(self.newly_failing)
            or self.error_rate.verdict == Verdict.REGRESSED
            or any(m.verdict == Verdict.REGRESSED and m.category in quality for m in self.metrics)
        )


class RunRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    project: str
    dataset_name: str
    dataset_hash: str
    config_hash: str
    finished_at: str


class RunComparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    comparison_schema_version: str = COMPARISON_SCHEMA_VERSION
    baseline: RunRef
    candidate: RunRef
    settings: ComparisonSettings
    same_dataset: bool
    # Metrics present in only one run, or with a different version/config, are excluded.
    excluded_metrics: dict[str, str]
    warnings: list[str]
    models: list[ModelComparison]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def newly_failing_count(self) -> int:
        return sum(len(m.newly_failing) for m in self.models)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def recovered_count(self) -> int:
        return sum(len(m.recovered) for m in self.models)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def regressed(self) -> bool:
        return any(m.regressed for m in self.models)
