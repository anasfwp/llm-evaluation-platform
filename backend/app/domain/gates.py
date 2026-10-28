"""Quality gate rules and their evaluation results.

A rule is either **absolute** (``operator`` + ``threshold``, e.g. mean
exact_match >= 0.8) or **relative** to a baseline run (``max_regression``,
e.g. mean exact_match may drop by at most 0.02, or p95 latency may rise by at
most 10%). The direction of "worse" comes from the metric's declared
direction. Any rule can be scoped to one model and/or to the cases carrying a
tag.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Run-level metrics computed from case statuses rather than from a metric implementation.
ERROR_RATE = "error_rate"

Aggregation = Literal["mean", "median", "p95", "min", "max", "total", "count", "overall"]
Operator = Literal["gte", "gt", "lte", "lt", "eq"]
RuleKind = Literal["absolute", "relative"]
RegressionUnit = Literal["absolute", "percent"]


class MissingMetricPolicy(StrEnum):
    FAIL = "fail"
    SKIP = "skip"
    WARN = "warn"


class GateRule(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metric: str = Field(min_length=1)
    aggregation: Aggregation
    kind: RuleKind = "absolute"
    # Absolute rules.
    operator: Operator | None = None
    threshold: float | None = None
    # Relative rules: the largest allowed change in the "worse" direction.
    max_regression: float | None = Field(default=None, ge=0)
    regression_unit: RegressionUnit = "absolute"
    # Restrict the rule to one model by its configured name; default is every model.
    model: str | None = None
    # Relative rules compare against the baseline model of the same name unless set.
    baseline_model: str | None = None
    # Evaluate the rule only over cases carrying this tag.
    tag: str | None = Field(default=None, min_length=1, max_length=100)
    missing_metric_policy: MissingMetricPolicy | None = None

    @model_validator(mode="after")
    def _consistent(self) -> GateRule:
        if self.metric == ERROR_RATE and self.aggregation != "overall":
            raise ValueError("error_rate only supports aggregation 'overall'")
        if self.metric != ERROR_RATE and self.aggregation == "overall":
            raise ValueError("aggregation 'overall' is only valid for error_rate")
        if self.kind == "absolute":
            if self.operator is None or self.threshold is None:
                raise ValueError("absolute rules need 'operator' and 'threshold'")
            if self.max_regression is not None or self.baseline_model is not None:
                raise ValueError("'max_regression'/'baseline_model' are only for relative rules")
        else:
            if self.max_regression is None:
                raise ValueError("relative rules need 'max_regression'")
            if self.operator is not None or self.threshold is not None:
                raise ValueError("relative rules use 'max_regression', not operator/threshold")
        return self


class GateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    name: str = Field(default="default", min_length=1, max_length=200)
    missing_metric_policy: MissingMetricPolicy = MissingMetricPolicy.FAIL
    rules: list[GateRule] = Field(min_length=1, max_length=200)

    @property
    def needs_baseline(self) -> bool:
        return any(rule.kind == "relative" for rule in self.rules)


class RuleOutcomeStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    WARNED = "warned"


class RuleOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    kind: RuleKind = "absolute"
    metric: str
    aggregation: str
    # For relative rules: "max_regression" and the allowed regression.
    operator: str
    threshold: float
    model: str
    tag: str | None = None
    actual: float | None
    # Relative rules only: the baseline value and the measured regression (positive = worse).
    baseline: float | None = None
    regression: float | None = None
    status: RuleOutcomeStatus
    reason: str | None = None

    @property
    def passed(self) -> bool:
        return self.status != RuleOutcomeStatus.FAILED


class GateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    gate_name: str
    passed: bool
    baseline_run_id: str | None = None
    results: list[RuleOutcome]
