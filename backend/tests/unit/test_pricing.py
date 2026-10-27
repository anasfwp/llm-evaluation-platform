from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.datasets import EvaluationCase
from app.domain.metrics import MetricStatus
from app.domain.models import NormalizedModelResponse
from app.domain.runs import MetricSelection
from app.evaluation.aggregation import summarize_metric
from app.evaluation.metrics.base import MetricInput
from app.evaluation.metrics.estimated_cost import EstimatedCost
from app.evaluation.metrics.latency import Latency
from app.evaluation.pricing import PriceEntry, PricingTable, default_pricing, estimate_cost
from app.evaluation.registry import freeze_selections
from tests.unit.test_aggregation import _result

CaseFactory = Callable[..., EvaluationCase]


def _entry(**fields: Any) -> dict[str, Any]:
    return {
        "provider": "acme",
        "model_id": "big",
        "input_per_million": 2.0,
        "output_per_million": 8.0,
        "effective_from": "2026-01-01",
        "source": "test",
        **fields,
    }


def _table(*entries: dict[str, Any]) -> PricingTable:
    return PricingTable.model_validate({"pricing_version": "t1", "entries": list(entries)})


def test_bundled_table_loads_and_prices_known_models() -> None:
    table = default_pricing()
    entry = table.find("anthropic", "claude-opus-5-5", date(2026, 10, 27))
    assert entry is not None
    assert (entry.input_per_million, entry.output_per_million) == (4.0, 20.0)
    assert table.find("anthropic", "claude-unknown", date(2026, 10, 27)) is None
    assert table.find("fake", "anything", date(2026, 10, 27)) is not None


def test_find_prefers_exact_model_and_latest_effective_entry() -> None:
    table = _table(
        _entry(model_id="*", input_per_million=99.0),
        _entry(effective_to="2026-06-01"),
        _entry(effective_from="2026-06-01", input_per_million=3.0),
    )
    found = table.find("acme", "big", date(2026, 3, 1))
    assert found is not None and found.input_per_million == 2.0
    found = table.find("acme", "big", date(2026, 7, 1))
    assert found is not None and found.input_per_million == 3.0
    wildcard = table.find("acme", "small", date(2026, 7, 1))
    assert wildcard is not None and wildcard.input_per_million == 99.0
    assert table.find("acme", "big", date(2025, 12, 31)) is None


def test_estimate_cost_and_long_context_rate() -> None:
    entry = PriceEntry.model_validate(
        _entry(
            long_context_threshold_tokens=1000,
            long_context_input_per_million=4.0,
            long_context_output_per_million=16.0,
        )
    )
    normal = estimate_cost(entry, 1000, 500)
    assert normal.long_context_rate is False
    assert normal.total == pytest.approx(1000 * 2 / 1e6 + 500 * 8 / 1e6)
    long = estimate_cost(entry, 1001, 500)
    assert long.long_context_rate is True
    assert long.input_cost == pytest.approx(1001 * 4 / 1e6)
    assert long.output_cost == pytest.approx(500 * 16 / 1e6)


@pytest.mark.parametrize(
    "fields",
    [
        {"long_context_threshold_tokens": 10},  # incomplete long-context tier
        {"effective_to": "2025-01-01"},  # ends before it starts
        {"input_per_million": -1},
    ],
)
def test_invalid_entries_rejected(fields: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PriceEntry.model_validate(_entry(**fields))


def test_duplicate_entries_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate pricing entries"):
        _table(_entry(), _entry(input_per_million=5.0))


def _cost_input(
    make_case: CaseFactory,
    *,
    model_id: str = "big",
    tokens: tuple[int | None, int | None] = (1, 1),
) -> MetricInput:
    response = NormalizedModelResponse(
        output_text="x",
        provider="acme",
        model_id=model_id,
        input_tokens=tokens[0],
        output_tokens=tokens[1],
    )
    return MetricInput(case=make_case(expected="x"), response=response, latency_ms=1.0)


def test_estimated_cost_scores_with_pricing_details(make_case: CaseFactory) -> None:
    metric = EstimatedCost({"pricing": _table(_entry()).model_dump(mode="json")})
    result = metric.evaluate(_cost_input(make_case, tokens=(1_000_000, 250_000)))
    assert result.status == MetricStatus.SCORED
    assert result.score == pytest.approx(2.0 + 2.0)
    assert result.details["pricing_version"] == "t1"
    assert result.details["price_effective_from"] == "2026-01-01"
    assert result.details["currency"] == "USD"
    assert result.details["is_estimate"] is True


def test_estimated_cost_not_applicable_without_usage_or_price(make_case: CaseFactory) -> None:
    metric = EstimatedCost({"pricing": _table(_entry()).model_dump(mode="json")})
    no_usage = metric.evaluate(_cost_input(make_case, tokens=(None, None)))
    assert no_usage.status == MetricStatus.NOT_APPLICABLE
    assert "usage" in no_usage.details["reason"]
    unpriced = metric.evaluate(_cost_input(make_case, model_id="other"))
    assert unpriced.status == MetricStatus.NOT_APPLICABLE
    assert "no price for acme/other" in unpriced.details["reason"]


def test_freeze_selections_pins_the_bundled_table() -> None:
    frozen = freeze_selections(
        [MetricSelection(name="estimated_cost"), MetricSelection(name="latency")]
    )
    pricing = frozen[0].config["pricing"]
    assert pricing["pricing_version"] == default_pricing().pricing_version
    assert frozen[1].config == {}
    explicit = {"pricing": _table(_entry()).model_dump(mode="json")}
    again = freeze_selections([MetricSelection(name="estimated_cost", config=explicit)])
    assert again[0].config == explicit  # an explicit table is never replaced


def test_total_is_only_aggregated_for_additive_metrics() -> None:
    def renamed(name: str) -> list[Any]:
        results = []
        for key, score in (("a", 0.25), ("b", 0.5)):
            case = _result(key, score)
            metrics = [m.model_copy(update={"metric_name": name}) for m in case.metrics]
            results.append(case.model_copy(update={"metrics": metrics}))
        return results

    assert summarize_metric(EstimatedCost(), renamed("estimated_cost")).total == 0.75
    assert summarize_metric(Latency(), renamed("latency")).total is None
