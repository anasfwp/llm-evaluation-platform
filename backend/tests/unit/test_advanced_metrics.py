from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from pydantic import ValidationError

from app.domain.datasets import Dataset, EvaluationCase, RetrievedContext
from app.domain.metrics import MetricResult, MetricStatus
from app.domain.models import NormalizedModelResponse
from app.evaluation.metrics.base import Metric, MetricInput
from app.evaluation.metrics.llm_judge import (
    JudgeContextRelevance,
    JudgeCorrectness,
    JudgeGroundedness,
    JudgeRelevance,
    parse_verdict,
)
from app.evaluation.metrics.retrieval import (
    ReciprocalRank,
    RetrievalPrecisionAtK,
    RetrievalRecallAtK,
)
from app.evaluation.metrics.text_similarity import TokenF1, token_f1
from app.evaluation.registry import build_metric

CaseFactory = Callable[..., EvaluationCase]
FAKE_JUDGE: dict[str, Any] = {
    "judge": {"provider": "fake", "model_id": "fake-judge", "parameters": {"mode": "judge"}}
}


def _input(case: EvaluationCase, actual: str = "Paris") -> MetricInput:
    response = NormalizedModelResponse(output_text=actual, provider="fake", model_id="m")
    return MetricInput(case=case, response=response, latency_ms=1.0)


def _score(metric: Metric, data: MetricInput) -> MetricResult:
    async def run() -> MetricResult:
        try:
            return await metric.evaluate_async(data)
        finally:
            await metric.aclose()

    return asyncio.run(run())


def _judge(overrides: dict[str, Any] | None = None, **settings: Any) -> dict[str, Any]:
    parameters: dict[str, Any] = {"mode": "judge"}
    if overrides:
        parameters["overrides"] = overrides
    return {
        "judge": {
            "provider": "fake",
            "model_id": "fake-judge",
            "parameters": parameters,
            **settings,
        }
    }


def _ranked(make_case: CaseFactory, ids: list[str], relevant: list[str] | None) -> EvaluationCase:
    return make_case(
        retrieved_contexts=[RetrievedContext(document_id=d, text=f"text {d}") for d in ids],
        relevant_document_ids=relevant,
    )


# token_f1


def test_token_f1_partial_overlap() -> None:
    precision, recall, f1 = token_f1("12", "The square root of 144 is 12.")
    assert precision == pytest.approx(1 / 7)
    assert recall == 1.0
    assert f1 == pytest.approx(0.25)


def test_token_f1_ignores_punctuation_and_case(make_case: CaseFactory) -> None:
    assert TokenF1().evaluate(_input(make_case(expected="H2O"), "h2o.")).score == 1.0


def test_token_f1_empty_output_scores_zero(make_case: CaseFactory) -> None:
    assert TokenF1().evaluate(_input(make_case(expected="Paris"), "")).score == 0.0


def test_token_f1_not_applicable_without_reference(make_case: CaseFactory) -> None:
    result = TokenF1().evaluate(_input(make_case(expected=None)))
    assert result.status == MetricStatus.NOT_APPLICABLE


# retrieval


def test_precision_at_k_uses_top_k_and_dedupes(make_case: CaseFactory) -> None:
    case = _ranked(make_case, ["a", "x", "a", "b", "y"], ["a", "b"])
    result = RetrievalPrecisionAtK({"k": 3}).evaluate(_input(case))
    # Deduplicated ranking a, x, b, y -> top 3 = a, x, b
    assert result.score == pytest.approx(2 / 3)
    assert result.details["hits"] == ["a", "b"]


def test_precision_uses_retrieved_count_when_fewer_than_k(make_case: CaseFactory) -> None:
    result = RetrievalPrecisionAtK({"k": 5}).evaluate(_input(_ranked(make_case, ["a", "x"], ["a"])))
    assert result.score == 0.5
    assert result.details["k_effective"] == 2


def test_precision_not_applicable_when_nothing_retrieved(make_case: CaseFactory) -> None:
    result = RetrievalPrecisionAtK().evaluate(_input(_ranked(make_case, [], ["a"])))
    assert result.status == MetricStatus.NOT_APPLICABLE


def test_recall_at_k(make_case: CaseFactory) -> None:
    case = _ranked(make_case, ["x", "a", "y", "b"], ["a", "b", "c"])
    result = RetrievalRecallAtK({"k": 2}).evaluate(_input(case))
    assert result.score == pytest.approx(1 / 3)
    assert result.details["missed"] == ["b", "c"]


def test_recall_is_zero_when_nothing_retrieved(make_case: CaseFactory) -> None:
    result = RetrievalRecallAtK().evaluate(_input(_ranked(make_case, [], ["a"])))
    assert result.status == MetricStatus.SCORED
    assert result.score == 0.0


def test_reciprocal_rank(make_case: CaseFactory) -> None:
    case = _ranked(make_case, ["x", "y", "a"], ["a"])
    assert ReciprocalRank().evaluate(_input(case)).score == pytest.approx(1 / 3)
    assert ReciprocalRank({"k": 2}).evaluate(_input(case)).score == 0.0


@pytest.mark.parametrize("metric_cls", [RetrievalPrecisionAtK, RetrievalRecallAtK, ReciprocalRank])
def test_retrieval_metrics_need_labels(make_case: CaseFactory, metric_cls: type[Metric]) -> None:
    result = metric_cls().evaluate(_input(_ranked(make_case, ["a"], None)))
    assert result.status == MetricStatus.NOT_APPLICABLE
    assert "relevant_document_ids" in result.details["reason"]


def test_empty_label_set_makes_recall_undefined(make_case: CaseFactory) -> None:
    result = RetrievalRecallAtK().evaluate(_input(_ranked(make_case, ["a"], [])))
    assert result.status == MetricStatus.NOT_APPLICABLE


def test_relevance_labels_do_not_change_existing_dataset_hashes(make_case: CaseFactory) -> None:
    plain = Dataset(schema_version="1.0", name="d", cases=[make_case()])
    raw = plain.model_dump(mode="json")
    for case in raw["cases"]:
        del case["relevant_document_ids"]
    assert Dataset.model_validate(raw).content_hash() == plain.content_hash()
    labelled = Dataset(
        schema_version="1.0", name="d", cases=[make_case(relevant_document_ids=["a"])]
    )
    assert labelled.content_hash() != plain.content_hash()


# LLM judge


def test_parse_verdict_tolerates_code_fences_and_rejects_bad_scores() -> None:
    assert parse_verdict('```json\n{"score": 4, "rationale": " ok "}\n```') == (4, "ok")
    assert parse_verdict('{"score": 6, "rationale": "x"}') is None
    assert parse_verdict('{"score": "4"}') is None
    assert parse_verdict("no json here") is None


def test_fake_judge_correctness_scores_and_records_provenance(make_case: CaseFactory) -> None:
    good = _score(JudgeCorrectness(FAKE_JUDGE), _input(make_case(expected="Paris"), "Paris"))
    assert good.status == MetricStatus.SCORED
    assert good.score == 5.0
    assert good.details["judge_model_id"] == "fake-judge"
    assert good.details["rubric_version"] == "1.0"
    assert good.details["criterion"] == "correctness"
    assert good.details["rationale"].startswith("fake judge")
    bad = _score(JudgeCorrectness(FAKE_JUDGE), _input(make_case(expected="Canberra"), "Sydney"))
    assert bad.score == 1.0


def test_judge_not_applicable_without_required_inputs(make_case: CaseFactory) -> None:
    case = make_case(expected=None)
    correctness = _score(JudgeCorrectness(FAKE_JUDGE), _input(case))
    groundedness = _score(JudgeGroundedness(FAKE_JUDGE), _input(case))
    assert correctness.status == MetricStatus.NOT_APPLICABLE
    assert groundedness.status == MetricStatus.NOT_APPLICABLE
    assert _score(JudgeRelevance(FAKE_JUDGE), _input(case)).status == MetricStatus.SCORED


def test_judge_groundedness_uses_context(make_case: CaseFactory) -> None:
    case = make_case(reference_context="Paris is the capital of France.")
    supported = _score(JudgeGroundedness(FAKE_JUDGE), _input(case, "Paris is the capital"))
    unsupported = _score(JudgeGroundedness(FAKE_JUDGE), _input(case, "Lyon has many bridges"))
    assert supported.score == 5.0
    assert unsupported.score == 1.0
    relevant = _score(JudgeContextRelevance(FAKE_JUDGE), _input(case))
    assert relevant.status == MetricStatus.SCORED


def test_unparseable_judge_output_is_an_error(make_case: CaseFactory) -> None:
    config = _judge({"case-1": {"output": "great answer"}})
    result = _score(JudgeRelevance(config), _input(make_case()))
    assert result.status == MetricStatus.ERROR
    assert result.details["error_code"] == "unparseable_judge_output"
    assert result.score is None


def test_judge_provider_errors_are_recorded_not_scored(make_case: CaseFactory) -> None:
    config = _judge({"case-1": {"error": "rate_limited"}}, max_retries=0)
    result = _score(JudgeRelevance(config), _input(make_case()))
    assert result.status == MetricStatus.ERROR
    assert result.details["error_code"] == "rate_limited"


def test_judge_call_budget(make_case: CaseFactory) -> None:
    metric = JudgeRelevance(_judge(max_calls=1))

    async def run() -> list[MetricResult]:
        results = [await metric.evaluate_async(_input(make_case(f"c{i}"))) for i in range(2)]
        await metric.aclose()
        return results

    first, second = asyncio.run(run())
    assert first.status == MetricStatus.SCORED
    assert second.status == MetricStatus.ERROR
    assert second.details["error_code"] == "budget_exhausted"


def test_judge_config_validation() -> None:
    with pytest.raises(ValidationError, match="unknown provider"):
        build_metric("llm_judge_relevance", None, {"judge": {"provider": "nope", "model_id": "x"}})
    with pytest.raises(ValidationError, match="system_prompt"):
        build_metric(
            "llm_judge_relevance",
            None,
            {
                "judge": {
                    "provider": "anthropic",
                    "model_id": "claude-haiku-5-5",
                    "parameters": {"system_prompt": "be nice"},
                }
            },
        )
    with pytest.raises(ValidationError):
        build_metric("llm_judge_relevance", None, {})


def test_judge_env_references_use_provider_defaults() -> None:
    metric = build_metric(
        "llm_judge_correctness",
        None,
        {"judge": {"provider": "anthropic", "model_id": "claude-haiku-5-5"}},
    )
    assert metric.env_references() == {"judge.secret_reference": "ANTHROPIC_API_KEY"}
    assert build_metric("llm_judge_correctness", None, FAKE_JUDGE).env_references() == {}
