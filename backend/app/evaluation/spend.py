"""Per-run spend limit: stop starting paid work once a run's estimated spend reaches its limit.

The tracker counts every paid call that returned usage: model calls, LLM judges,
and embeddings. It fails closed. A run with a limit will not start if a billed
model has no price, and it stops if a provider stops reporting usage, because
a limit that silently undercounts is worse than none.

This is a guard rail, not a billing control. Spend is estimated from the pricing
table, calls already in flight finish after the limit is reached, and failed
calls count as free even though a provider may bill a request that timed out.
Keep provider-side limits as well.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.models import ModelConfigSnapshot
from app.domain.runs import EvalConfig, SpendSummary
from app.evaluation.metrics.base import Metric
from app.evaluation.metrics.estimated_cost import EstimatedCost
from app.evaluation.pricing import PricingTable, default_pricing, estimate_cost
from app.utils.time import utc_now


def spend_pricing(metrics: Sequence[Metric]) -> PricingTable:
    """The run's ``estimated_cost`` table when it has one, so both report the same prices."""
    for metric in metrics:
        if isinstance(metric, EstimatedCost):
            return metric.pricing
    return default_pricing()


def unpriced_models(models: Sequence[ModelConfigSnapshot], metrics: Sequence[Metric]) -> list[str]:
    """Billed models with no current price, as sorted ``provider/model_id`` labels."""
    pricing = spend_pricing(metrics)
    today = utc_now().date()
    billed = {(model.provider, model.model_id) for model in models}
    billed.update(pair for metric in metrics for pair in metric.billed_models())
    return sorted(
        f"{provider}/{model_id}"
        for provider, model_id in billed
        if pricing.find(provider, model_id, today) is None
    )


def unpriced_message(labels: Sequence[str]) -> str:
    return (
        f"cannot enforce max_spend_usd: no price for {', '.join(labels)}. "
        "Add it to the estimated_cost metric's pricing table, or remove the limit."
    )


class SpendTracker:
    def __init__(self, limit_usd: float, pricing: PricingTable) -> None:
        self.limit_usd = limit_usd
        self.pricing = pricing
        self.spent_usd = 0.0
        self.skipped_work = False
        self._untrackable: str | None = None

    @property
    def exhausted(self) -> bool:
        return self._untrackable is not None or self.spent_usd >= self.limit_usd

    def charge(
        self,
        provider: str,
        model_id: str,
        input_tokens: int | None,
        output_tokens: int | None,
    ) -> None:
        label = f"{provider}/{model_id}"
        if input_tokens is None or output_tokens is None:
            self._untrackable = self._untrackable or (
                f"{label} did not report token usage, so spend could not be tracked"
            )
            return
        entry = self.pricing.find(provider, model_id, utc_now().date())
        if entry is None:
            self._untrackable = self._untrackable or (
                f"{label} has no price, so spend could not be tracked"
            )
            return
        self.spent_usd += estimate_cost(entry, input_tokens, output_tokens).total

    def summary(self) -> SpendSummary:
        stop_reason = None
        if self.skipped_work:
            stop_reason = self._untrackable or (
                f"estimated spend ${self.spent_usd:.6f} reached the ${self.limit_usd:.6f} limit"
            )
        return SpendSummary(
            limit_usd=self.limit_usd,
            estimated_usd=round(self.spent_usd, 10),
            stop_reason=stop_reason,
        )


def build_spend_tracker(config: EvalConfig, metrics: Sequence[Metric]) -> SpendTracker | None:
    """A tracker for a run with a limit; ``None`` leaves the run's behaviour unchanged."""
    limit = config.run.max_spend_usd
    return None if limit is None else SpendTracker(limit, spend_pricing(metrics))
