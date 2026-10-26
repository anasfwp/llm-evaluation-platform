"""Metric registry: maps stable metric names to implementations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.evaluation.metrics.base import Metric
from app.evaluation.metrics.exact_match import ExactMatch
from app.evaluation.metrics.latency import Latency

METRICS: dict[str, type[Metric]] = {cls.name: cls for cls in (ExactMatch, Latency)}


def build_metric(name: str, version: str | None, config: Mapping[str, Any]) -> Metric:
    """Instantiate a metric, raising ``ValueError`` for unknown names, versions, or config."""
    try:
        cls = METRICS[name]
    except KeyError:
        supported = ", ".join(sorted(METRICS))
        raise ValueError(f"unknown metric '{name}' (supported: {supported})") from None
    if version is not None and version != cls.version:
        raise ValueError(
            f"metric '{name}' version '{version}' is not available (implemented: {cls.version})"
        )
    return cls(config)
