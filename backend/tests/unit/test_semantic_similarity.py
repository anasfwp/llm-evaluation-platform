from __future__ import annotations

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest

from app.domain.datasets import EvaluationCase
from app.domain.metrics import MetricResult, MetricStatus
from app.domain.models import NormalizedModelResponse
from app.evaluation.metrics.base import MetricInput
from app.evaluation.metrics.semantic_similarity import SemanticSimilarity
from app.providers.embeddings import EmbeddingConfig, HTTPEmbeddingClient, cosine_similarity

CaseFactory = Callable[..., EvaluationCase]
FAKE = {"embedding": {"provider": "fake", "model_id": "fake-embed"}}


def _score(metric: SemanticSimilarity, case: EvaluationCase, actual: str) -> MetricResult:
    response = NormalizedModelResponse(output_text=actual, provider="fake", model_id="m")

    async def run() -> MetricResult:
        try:
            return await metric.evaluate_async(MetricInput(case, response, 1.0))
        finally:
            await metric.aclose()

    return asyncio.run(run())


def test_cosine_similarity() -> None:
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    assert cosine_similarity([1, 0], [-1, 0]) == -1.0
    assert cosine_similarity([0, 0], [1, 0]) is None
    with pytest.raises(ValueError, match="dimensions"):
        cosine_similarity([1], [1, 2])


def test_fake_embeddings_are_lexical_and_deterministic(make_case: CaseFactory) -> None:
    case = make_case(expected="Paris is the capital")
    same = _score(SemanticSimilarity(FAKE), case, "the capital is Paris.")
    different = _score(SemanticSimilarity(FAKE), case, "Bananas grow fast")
    assert same.score == pytest.approx(1.0)
    assert same.details["embedding_method"] == "hashed_bag_of_words"
    assert different.score is not None and different.score < 0.5


def test_not_applicable_without_reference_and_zero_for_empty(make_case: CaseFactory) -> None:
    missing = _score(SemanticSimilarity(FAKE), make_case(expected=None), "x")
    assert missing.status == MetricStatus.NOT_APPLICABLE
    empty = _score(SemanticSimilarity(FAKE), make_case(expected="Paris"), "  ")
    assert empty.score == 0.0


def test_env_references() -> None:
    compatible = SemanticSimilarity(
        {"embedding": {"provider": "openai_compatible", "model_id": "e"}}
    )
    assert compatible.env_references() == {
        "embedding.secret_reference": "OPENAI_COMPATIBLE_API_KEY",
        "embedding.base_url_env": "OPENAI_COMPATIBLE_BASE_URL",
    }
    assert SemanticSimilarity(FAKE).env_references() == {}


def _http_client(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> HTTPEmbeddingClient:
    monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", "http://embed.test/v1/")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "test-key")
    config = EmbeddingConfig(provider="openai_compatible", model_id="embed-1")
    transport = httpx.MockTransport(handler)
    return HTTPEmbeddingClient(config, httpx.AsyncClient(transport=transport))


def test_http_embeddings_request_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": 1, "embedding": [0.0, 1.0]},
                    {"index": 0, "embedding": [1.0, 0.0]},
                ],
                "usage": {"prompt_tokens": 7},
            },
        )

    client = _http_client(monkeypatch, handler)
    result = asyncio.run(client.embed(["a", "b"]))
    assert result.vectors == [[1.0, 0.0], [0.0, 1.0]]  # reordered by index
    assert result.input_tokens == 7
    assert str(seen[0].url) == "http://embed.test/v1/embeddings"
    assert seen[0].headers["authorization"] == "Bearer test-key"
    assert json.loads(seen[0].content) == {"model": "embed-1", "input": ["a", "b"]}


def test_http_embedding_errors_become_metric_errors(
    monkeypatch: pytest.MonkeyPatch, make_case: CaseFactory
) -> None:
    client = _http_client(monkeypatch, lambda _: httpx.Response(429, json={"error": {}}))
    metric = SemanticSimilarity({"embedding": {"provider": "openai_compatible", "model_id": "e"}})
    metric._client = client
    result = _score(metric, make_case(expected="Paris"), "Paris")
    assert result.status == MetricStatus.ERROR
    assert result.details["error_code"] == "rate_limited"


def test_openai_without_key_is_an_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = HTTPEmbeddingClient(EmbeddingConfig(provider="openai", model_id="e"))
    with pytest.raises(Exception, match="OPENAI_API_KEY"):
        asyncio.run(client.embed(["a"]))
    asyncio.run(client.aclose())
