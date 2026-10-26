from __future__ import annotations

from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.evaluation.metrics.base import Metric, MetricInput


class Latency(Metric):
    name = "latency"
    version = "1.0"
    category = MetricCategory.PERFORMANCE
    direction = MetricDirection.LOWER_IS_BETTER
    unit = "ms"
    score_range = (0.0, None)
    required_inputs = ("latency_ms",)
    description = (
        "Wall-clock time of the successful model call in milliseconds, measured by the "
        "engine around the adapter call (final attempt only; retries are not included)."
    )

    def evaluate(self, data: MetricInput) -> MetricResult:
        if data.latency_ms is None:
            return self.not_applicable("latency was not measured")
        return self.scored(round(data.latency_ms, 3))
