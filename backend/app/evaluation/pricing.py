"""Versioned model pricing used to estimate the cost of model calls.

Prices change, so every estimate records the pricing version and the entry's
effective date, and the table used by a run is frozen into its configuration
snapshot (and therefore its config hash). Estimates are only as accurate as
the table and the provider's usage reporting; they are never billing data.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

DEFAULT_PRICING_PATH = Path(__file__).with_name("default_pricing.yaml")
# Matches any model of a provider; an exact model_id entry always wins.
ANY_MODEL = "*"


class PriceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    input_per_million: float = Field(ge=0)
    output_per_million: float = Field(ge=0)
    # Optional higher rate when a prompt exceeds a size threshold (applies to the whole call).
    long_context_threshold_tokens: int | None = Field(default=None, ge=1)
    long_context_input_per_million: float | None = Field(default=None, ge=0)
    long_context_output_per_million: float | None = Field(default=None, ge=0)
    effective_from: date
    effective_to: date | None = None
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def _consistent(self) -> PriceEntry:
        tier = (
            self.long_context_threshold_tokens,
            self.long_context_input_per_million,
            self.long_context_output_per_million,
        )
        if any(v is not None for v in tier) and any(v is None for v in tier):
            raise ValueError("long-context pricing needs threshold, input and output rates")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self

    def is_effective(self, on: date) -> bool:
        return self.effective_from <= on and (self.effective_to is None or on < self.effective_to)


@dataclass(frozen=True)
class CostBreakdown:
    input_cost: float
    output_cost: float
    long_context_rate: bool

    @property
    def total(self) -> float:
        return self.input_cost + self.output_cost


class PricingTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    pricing_version: str = Field(min_length=1, max_length=50)
    currency: Literal["USD"] = "USD"
    entries: list[PriceEntry] = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _unique(self) -> PricingTable:
        keys = [(e.provider, e.model_id, e.effective_from) for e in self.entries]
        duplicates = {key for key in keys if keys.count(key) > 1}
        if duplicates:
            listed = ", ".join(f"{p}/{m} from {d}" for p, m, d in sorted(duplicates))
            raise ValueError(f"duplicate pricing entries: {listed}")
        return self

    def find(self, provider: str, model_id: str, on: date) -> PriceEntry | None:
        """The entry in effect on ``on``: exact model first, then the provider wildcard."""
        for wanted in (model_id, ANY_MODEL):
            candidates = [
                e
                for e in self.entries
                if e.provider == provider and e.model_id == wanted and e.is_effective(on)
            ]
            if candidates:
                return max(candidates, key=lambda e: e.effective_from)
        return None


def estimate_cost(entry: PriceEntry, input_tokens: int, output_tokens: int) -> CostBreakdown:
    long_context = (
        entry.long_context_threshold_tokens is not None
        and input_tokens > entry.long_context_threshold_tokens
    )
    if long_context:
        assert entry.long_context_input_per_million is not None
        assert entry.long_context_output_per_million is not None
        input_rate = entry.long_context_input_per_million
        output_rate = entry.long_context_output_per_million
    else:
        input_rate, output_rate = entry.input_per_million, entry.output_per_million
    return CostBreakdown(
        input_cost=input_tokens * input_rate / 1_000_000,
        output_cost=output_tokens * output_rate / 1_000_000,
        long_context_rate=long_context,
    )


def load_pricing(path: Path) -> PricingTable:
    with path.open(encoding="utf-8") as handle:
        return PricingTable.model_validate(yaml.safe_load(handle))


@lru_cache
def default_pricing() -> PricingTable:
    """The pricing table bundled with this software version."""
    return load_pricing(DEFAULT_PRICING_PATH)
