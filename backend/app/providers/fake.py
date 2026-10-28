"""Deterministic fake provider for tests, CI, and demos. No network, no credentials.

Behaviour is fully determined by the model parameters:

- ``mode: expected`` answers each case with its ``expected_output`` (the
  adapter is built with the dataset so it can act as an oracle);
  ``echo_input`` answers with the input's string values; ``constant``
  answers with ``constant_output``.
- ``overrides`` replaces the answer for specific ``case_key`` values with a
  fixed ``output`` or a simulated ``error`` category, which is how demos
  model a weaker model or provider failures.
- ``latency_ms`` adds a real ``asyncio.sleep`` so latency metrics have
  something to measure.
- ``mode: judge`` acts as a deterministic LLM judge for the ``llm_judge_*``
  metrics: it answers with a JSON verdict whose score is a crude lexical
  heuristic (the share of the judged text's words found in the evidence, or
  "non-empty" when there is no evidence). It shows how the pipeline works; it
  is not a quality signal.

Token counts are a whitespace approximation and are labelled as such.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any, ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.datasets import Dataset
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.providers.base import BaseProvider, ProviderError


class FakeOverride(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output: str | None = None
    error: ProviderErrorCategory | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> FakeOverride:
        if (self.output is None) == (self.error is None):
            raise ValueError("an override needs exactly one of 'output' or 'error'")
        return self


class FakeParameters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Literal["expected", "echo_input", "constant", "judge"] = "expected"
    constant_output: str = ""
    latency_ms: float = Field(default=0, ge=0, le=60_000)
    overrides: dict[str, FakeOverride] = Field(default_factory=dict)


class FakeProvider(BaseProvider):
    provider_name: ClassVar[str] = "fake"
    Parameters: ClassVar[type[BaseModel]] = FakeParameters

    def __init__(self, parameters: FakeParameters, expected_outputs: dict[str, str | None]) -> None:
        self._params = parameters
        self._expected = expected_outputs

    @classmethod
    def from_config(cls, model_config: ModelConfigSnapshot, *, dataset: Dataset) -> Self:
        params = FakeParameters.model_validate(model_config.parameters)
        expected = {case.case_key: case.expected_output for case in dataset.cases}
        return cls(params, expected)

    async def generate(
        self,
        *,
        request: ModelRequest,
        model_config: ModelConfigSnapshot,
        timeout_seconds: float,
    ) -> NormalizedModelResponse:
        if self._params.latency_ms:
            await asyncio.sleep(self._params.latency_ms / 1000)

        override = self._params.overrides.get(request.case_key)
        if override is not None and override.error is not None:
            raise ProviderError(override.error, f"simulated {override.error} from fake provider")

        if override is not None and override.output is not None:
            output = override.output
        elif self._params.mode == "expected":
            output = self._expected.get(request.case_key) or ""
        elif self._params.mode == "judge":
            output = _fake_verdict(request.input_data)
        elif self._params.mode == "echo_input":
            output = " ".join(_string_values(request.input_data))
        else:
            output = self._params.constant_output

        return NormalizedModelResponse(
            output_text=output,
            provider=self.provider_name,
            model_id=model_config.model_id,
            input_tokens=sum(len(v.split()) for v in _string_values(request.input_data)),
            output_tokens=len(output.split()),
            provider_request_id=f"fake-{request.case_key}",
            finish_reason="stop",
            raw_metadata={"mode": self._params.mode, "usage_method": "whitespace_approximation"},
        )


_WORD = re.compile(r"\w+")


def _fake_verdict(input_data: dict[str, Any]) -> str:
    subject = set(_WORD.findall(str(input_data.get("judge_subject", "")).casefold()))
    evidence = set(_WORD.findall(str(input_data.get("judge_evidence", "")).casefold()))
    if not subject:
        score, rationale = 1, "fake judge: nothing to judge"
    elif not evidence:
        score, rationale = 5, "fake judge: non-empty and no evidence to check against"
    else:
        support = len(subject & evidence) / len(subject)
        score = 1 + round(4 * support)
        rationale = f"fake judge: {support:.0%} of words found in the evidence"
    return json.dumps({"score": score, "rationale": rationale})


def _string_values(data: Any) -> list[str]:
    if isinstance(data, str):
        return [data]
    if isinstance(data, dict):
        return [s for value in data.values() for s in _string_values(value)]
    if isinstance(data, list):
        return [s for value in data for s in _string_values(value)]
    return []
