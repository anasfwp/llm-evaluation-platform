from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.evaluation.metrics.base import Metric, MetricInput
from app.evaluation.normalization import normalize_text


class ExactMatchConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    normalize: bool = True


class ExactMatch(Metric):
    name = "exact_match"
    version = "1.0"
    category = MetricCategory.ANSWER_QUALITY
    direction = MetricDirection.HIGHER_IS_BETTER
    score_range = (0.0, 1.0)
    required_inputs = ("expected_output", "actual_output")
    description = (
        "1.0 if the output equals the expected output after normalization "
        "(NFKC, casefold, whitespace collapse, surrounding punctuation stripped), else 0.0."
    )
    Config: ClassVar[type[BaseModel]] = ExactMatchConfig

    def evaluate(self, data: MetricInput) -> MetricResult:
        expected = data.case.expected_output
        if expected is None:
            return self.not_applicable("case has no expected_output")
        actual = data.response.output_text
        assert isinstance(self.config, ExactMatchConfig)
        if self.config.normalize:
            expected, actual = normalize_text(expected), normalize_text(actual)
        return self.scored(
            1.0 if expected == actual else 0.0,
            normalized=self.config.normalize,
            compared_expected=expected,
            compared_actual=actual,
        )
