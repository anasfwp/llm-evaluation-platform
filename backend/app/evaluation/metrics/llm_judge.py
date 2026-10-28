"""LLM-as-judge metrics: a judge model grades one criterion on a versioned 1-5 rubric.

Judge scores are estimates. They can be biased (towards long or confident
answers, or towards the judge's own model family) and vary between calls, so
every result records the judge provider/model, rubric version, rationale and
the judge's token usage, and a failed or unparseable judgement is an ``error``
result rather than a guessed score.

The judge is any registered provider. With ``provider: fake`` and
``parameters: {mode: judge}`` it is a deterministic lexical heuristic, which
exercises the whole pipeline in tests and CI without credentials.
"""

from __future__ import annotations

import asyncio
import json
import re
from abc import abstractmethod
from dataclasses import dataclass
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.datasets import Dataset, EvaluationCase
from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.domain.models import (
    SECRET_REFERENCE_PATTERN,
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.evaluation.metrics.base import AsyncMetric, MetricInput
from app.evaluation.rubrics import RUBRICS, SCALE_MAX, SCALE_MIN, SYSTEM_PROMPT, Rubric
from app.providers.base import BaseProvider, ProviderError
from app.providers.prompting import render_prompt
from app.providers.registry import get_provider
from app.utils.redaction import safe_error_message

MAX_RATIONALE_CHARS = 500
# Judge adapters are built without the evaluated dataset; providers only need a valid one.
_JUDGE_PLACEHOLDER_DATASET = Dataset(
    schema_version="1.0",
    name="judge",
    cases=[EvaluationCase(case_key="judge", input={"prompt": "judge"})],
)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)
# The judge controls the prompt; letting a config override it would change the rubric.
_RESERVED_PARAMETERS = ("system_prompt", "prompt_template")


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    secret_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    timeout_seconds: float = Field(default=60, gt=0, le=600)
    max_concurrency: int = Field(default=2, ge=1, le=32)
    max_retries: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=1.0, ge=0, le=30)
    # Spend guard: at most this many judge calls per run for this metric (retries included).
    max_calls: int | None = Field(default=None, ge=1, le=1_000_000)

    @model_validator(mode="after")
    def _valid_for_provider(self) -> JudgeConfig:
        try:
            provider = get_provider(self.provider)
        except KeyError as exc:
            raise ValueError(str(exc.args[0])) from None
        reserved = [key for key in _RESERVED_PARAMETERS if key in self.parameters]
        if reserved:
            raise ValueError(f"judge parameters must not set {', '.join(reserved)}")
        provider.Parameters.model_validate(self._provider_parameters(provider))
        return self

    def _provider_parameters(self, provider: type[BaseProvider]) -> dict[str, Any]:
        parameters = dict(self.parameters)
        if "system_prompt" in provider.Parameters.model_fields:
            parameters["system_prompt"] = SYSTEM_PROMPT
        return parameters

    def snapshot(self) -> ModelConfigSnapshot:
        return ModelConfigSnapshot(
            name="judge",
            provider=self.provider,
            model_id=self.model_id,
            parameters=self._provider_parameters(get_provider(self.provider)),
            timeout_seconds=self.timeout_seconds,
            secret_reference=self.secret_reference,
        )


class LLMJudgeMetricConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    judge: JudgeConfig


@dataclass(frozen=True)
class _JudgeFailure:
    code: str
    message: str


class _JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    score: int = Field(ge=SCALE_MIN, le=SCALE_MAX, strict=True)
    rationale: str = ""


def parse_verdict(text: str) -> tuple[int, str] | None:
    """Extract ``(score, rationale)`` from the judge output, tolerating code fences."""
    match = _JSON_OBJECT.search(text)
    if match is None:
        return None
    try:
        verdict = _JudgeVerdict.model_validate(json.loads(match.group(0)))
    except ValueError:  # json.JSONDecodeError and pydantic.ValidationError
        return None
    return verdict.score, verdict.rationale.strip()[:MAX_RATIONALE_CHARS]


class _LLMJudge(AsyncMetric):
    """Shared judge pipeline; subclasses pick the rubric and the material shown to the judge."""

    category = MetricCategory.ANSWER_QUALITY
    direction = MetricDirection.HIGHER_IS_BETTER
    score_range = (float(SCALE_MIN), float(SCALE_MAX))
    Config: ClassVar[type[BaseModel]] = LLMJudgeMetricConfig
    criterion: ClassVar[str]

    def __init__(self, config: Any = None) -> None:
        super().__init__(config)
        self._adapter: BaseProvider | None = None
        # Created on first use so it belongs to the running event loop.
        self._limit: asyncio.Semaphore | None = None
        self._calls = 0

    @property
    def judge(self) -> JudgeConfig:
        assert isinstance(self.config, LLMJudgeMetricConfig)
        return self.config.judge

    @property
    def rubric(self) -> Rubric:
        return RUBRICS[self.criterion]

    def env_references(self) -> dict[str, str]:
        judge = self.judge
        references = get_provider(judge.provider).env_references(
            judge.parameters, judge.secret_reference
        )
        return {f"judge.{location}": name for location, name in references.items()}

    @abstractmethod
    def material(self, data: MetricInput) -> list[tuple[str, str]] | str:
        """The tagged sections shown to the judge, or the reason the metric is not applicable."""

    # Which section the deterministic fake judge checks for support, and against what.
    fake_subject: ClassVar[str] = "response"
    fake_evidence: ClassVar[str | None] = None

    async def evaluate_async(self, data: MetricInput) -> MetricResult:
        material = self.material(data)
        if isinstance(material, str):
            return self.not_applicable(material)
        sections = dict(material)
        request = ModelRequest(
            case_key=data.case.case_key,
            input_data={
                "prompt": self.rubric.render(material),
                # Structured copies for the deterministic fake judge; real providers send
                # only "prompt" (see app.providers.prompting.render_prompt).
                "judge_criterion": self.criterion,
                "judge_subject": sections.get(self.fake_subject, ""),
                "judge_evidence": sections.get(self.fake_evidence or "", ""),
            },
        )
        provenance = {
            "criterion": self.criterion,
            "rubric_version": self.rubric.version,
            "judge_provider": self.judge.provider,
            "judge_model_id": self.judge.model_id,
        }
        if self._limit is None:
            self._limit = asyncio.Semaphore(self.judge.max_concurrency)
        async with self._limit:
            outcome = await self._call(request)
        if isinstance(outcome, _JudgeFailure):
            return self.error(outcome.code, safe_error_message(outcome.message), **provenance)
        response, attempts = outcome
        usage = {
            "judge_input_tokens": response.input_tokens,
            "judge_output_tokens": response.output_tokens,
            "judge_attempts": attempts,
        }
        verdict = parse_verdict(response.output_text)
        if verdict is None:
            return self.error(
                "unparseable_judge_output",
                "the judge did not return a JSON object with an integer score from 1 to 5",
                judge_output_excerpt=safe_error_message(response.output_text, max_length=200),
                **provenance,
                **usage,
            )
        score, rationale = verdict
        return self.scored(float(score), rationale=rationale, scale="1-5", **provenance, **usage)

    async def _call(
        self, request: ModelRequest
    ) -> tuple[NormalizedModelResponse, int] | _JudgeFailure:
        judge = self.judge
        snapshot = judge.snapshot()
        if self._adapter is None:
            self._adapter = get_provider(judge.provider).from_config(
                snapshot, dataset=_JUDGE_PLACEHOLDER_DATASET
            )
        error = ProviderError(ProviderErrorCategory.UNKNOWN, "judge was not called")
        for attempt in range(1, judge.max_retries + 2):
            if judge.max_calls is not None and self._calls >= judge.max_calls:
                return _JudgeFailure(
                    "budget_exhausted", f"judge call budget exhausted (max_calls={judge.max_calls})"
                )
            self._calls += 1
            try:
                response = await asyncio.wait_for(
                    self._adapter.generate(
                        request=request,
                        model_config=snapshot,
                        timeout_seconds=judge.timeout_seconds,
                    ),
                    timeout=judge.timeout_seconds,
                )
                return response, attempt
            except TimeoutError:
                error = ProviderError(
                    ProviderErrorCategory.TIMEOUT,
                    f"no judge response within {judge.timeout_seconds}s",
                )
            except ProviderError as exc:
                error = exc
            if not error.category.is_transient or attempt > judge.max_retries:
                break
            backoff = judge.retry_backoff_seconds * 2 ** (attempt - 1)
            await asyncio.sleep(max(backoff, error.retry_after_seconds or 0.0))
        return _JudgeFailure(str(error.category), error.message)

    async def aclose(self) -> None:
        self._limit = None
        if self._adapter is not None:
            adapter, self._adapter = self._adapter, None
            await adapter.aclose()


def _question(case: EvaluationCase) -> str:
    return render_prompt(case.input, None)


def _context(case: EvaluationCase) -> str | None:
    """The reference context and retrieved chunks, or ``None`` when the case has neither."""
    parts: list[str] = []
    if case.reference_context:
        parts.append(case.reference_context)
    parts += [f"[{c.document_id}] {c.text}" for c in case.retrieved_contexts if c.text.strip()]
    return "\n\n".join(parts) if parts else None


class JudgeCorrectness(_LLMJudge):
    name = "llm_judge_correctness"
    version = "1.0"
    criterion = "correctness"
    fake_evidence = "reference_answer"
    required_inputs = ("input", "expected_output", "actual_output", "judge model")
    description = (
        "Judge model's 1-5 rating of whether the output agrees with the expected answer "
        "(rubric correctness v1.0). An estimate, not ground truth. Not applicable without "
        "expected_output."
    )

    def material(self, data: MetricInput) -> list[tuple[str, str]] | str:
        if data.case.expected_output is None:
            return "case has no expected_output"
        return [
            ("input", _question(data.case)),
            ("reference_answer", data.case.expected_output),
            ("response", data.response.output_text),
        ]


class JudgeRelevance(_LLMJudge):
    name = "llm_judge_relevance"
    version = "1.0"
    criterion = "relevance"
    required_inputs = ("input", "actual_output", "judge model")
    description = (
        "Judge model's 1-5 rating of whether the output addresses the input "
        "(rubric relevance v1.0). Does not judge factual accuracy. An estimate."
    )

    def material(self, data: MetricInput) -> list[tuple[str, str]] | str:
        return [("input", _question(data.case)), ("response", data.response.output_text)]


class JudgeInstructionAdherence(_LLMJudge):
    name = "llm_judge_instruction_adherence"
    version = "1.0"
    criterion = "instruction_adherence"
    required_inputs = ("input", "actual_output", "judge model")
    description = (
        "Judge model's 1-5 rating of whether the output follows the explicit instructions in "
        "the input, such as format or length (rubric instruction_adherence v1.0). An estimate."
    )

    def material(self, data: MetricInput) -> list[tuple[str, str]] | str:
        return [("input", _question(data.case)), ("response", data.response.output_text)]


class JudgeGroundedness(_LLMJudge):
    name = "llm_judge_groundedness"
    version = "1.0"
    criterion = "groundedness"
    fake_evidence = "context"
    required_inputs = ("reference_context or retrieved_contexts", "actual_output", "judge model")
    description = (
        "RAG faithfulness: judge model's 1-5 rating of whether every claim in the output is "
        "supported by the case's context (rubric groundedness v1.0). Not applicable without "
        "reference_context or retrieved_contexts text. An estimate."
    )

    def material(self, data: MetricInput) -> list[tuple[str, str]] | str:
        context = _context(data.case)
        if context is None:
            return "case has no reference_context or retrieved_contexts text"
        return [
            ("input", _question(data.case)),
            ("context", context),
            ("response", data.response.output_text),
        ]


class JudgeContextRelevance(_LLMJudge):
    name = "llm_judge_context_relevance"
    version = "1.0"
    criterion = "context_relevance"
    category = MetricCategory.RETRIEVAL_QUALITY
    fake_subject = "input"
    fake_evidence = "context"
    required_inputs = ("input", "reference_context or retrieved_contexts", "judge model")
    description = (
        "Judge model's 1-5 rating of whether the retrieved context contains what is needed to "
        "answer the input (rubric context_relevance v1.0); the output is not judged. Not "
        "applicable without context text. An estimate."
    )

    def material(self, data: MetricInput) -> list[tuple[str, str]] | str:
        context = _context(data.case)
        if context is None:
            return "case has no reference_context or retrieved_contexts text"
        return [("input", _question(data.case)), ("context", context)]


JUDGE_METRICS: tuple[type[_LLMJudge], ...] = (
    JudgeCorrectness,
    JudgeRelevance,
    JudgeInstructionAdherence,
    JudgeGroundedness,
    JudgeContextRelevance,
)
