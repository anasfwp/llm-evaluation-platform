"""Metric registry: maps stable metric names to implementations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.runs import MetricSelection
from app.evaluation.metrics.base import Metric
from app.evaluation.metrics.estimated_cost import EstimatedCost
from app.evaluation.metrics.exact_match import ExactMatch
from app.evaluation.metrics.latency import Latency
from app.evaluation.pricing import default_pricing

METRICS: dict[str, type[Metric]] = {cls.name: cls for cls in (ExactMatch, Latency, EstimatedCost)}


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


def freeze_selections(selections: Sequence[MetricSelection]) -> list[MetricSelection]:
    """Pin run-time defaults into metric configs before a run is snapshotted.

    ``estimated_cost`` without an explicit table gets the bundled pricing table,
    so the run's snapshot and config hash record the exact prices used.
    """
    frozen: list[MetricSelection] = []
    for selection in selections:
        if selection.name == EstimatedCost.name and "pricing" not in selection.config:
            pricing = default_pricing().model_dump(mode="json")
            selection = selection.model_copy(
                update={"config": {**selection.config, "pricing": pricing}}
            )
        frozen.append(selection)
    return frozen
