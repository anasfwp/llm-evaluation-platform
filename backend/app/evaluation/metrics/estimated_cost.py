from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.evaluation.metrics.base import Metric, MetricInput
from app.evaluation.pricing import PricingTable, default_pricing, estimate_cost
from app.utils.time import utc_now


class EstimatedCostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Filled in with the bundled table when a run is created, so the snapshot
    # records exactly which prices produced its estimates.
    pricing: PricingTable | None = None


class EstimatedCost(Metric):
    name = "estimated_cost"
    version = "1.0"
    category = MetricCategory.COST
    direction = MetricDirection.LOWER_IS_BETTER
    unit = "USD"
    score_range = (0.0, None)
    required_inputs = ("input_tokens", "output_tokens", "pricing entry")
    description = (
        "Estimated cost of the successful model call: provider-reported input and output "
        "tokens times the per-million-token prices in the run's pricing table. Not billing "
        "data. Not applicable when usage is not reported or the model has no price."
    )
    Config = EstimatedCostConfig
    aggregate_total: ClassVar[bool] = True

    @property
    def pricing(self) -> PricingTable:
        assert isinstance(self.config, EstimatedCostConfig)
        return self.config.pricing or default_pricing()

    def evaluate(self, data: MetricInput) -> MetricResult:
        response = data.response
        if response.input_tokens is None or response.output_tokens is None:
            return self.not_applicable("the provider did not report token usage")
        pricing = self.pricing
        entry = pricing.find(response.provider, response.model_id, utc_now().date())
        if entry is None:
            return self.not_applicable(
                f"no price for {response.provider}/{response.model_id} "
                f"in pricing version {pricing.pricing_version}"
            )
        cost = estimate_cost(entry, response.input_tokens, response.output_tokens)
        return self.scored(
            round(cost.total, 10),
            input_cost=round(cost.input_cost, 10),
            output_cost=round(cost.output_cost, 10),
            currency=pricing.currency,
            pricing_version=pricing.pricing_version,
            price_effective_from=entry.effective_from.isoformat(),
            long_context_rate=cost.long_context_rate,
            is_estimate=True,
        )
