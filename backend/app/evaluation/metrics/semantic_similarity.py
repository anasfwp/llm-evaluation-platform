from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict

from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.evaluation.metrics.base import AsyncMetric, MetricInput
from app.providers.base import ProviderError
from app.providers.embeddings import (
    EmbeddingClient,
    EmbeddingConfig,
    build_embedding_client,
    cosine_similarity,
)
from app.utils.redaction import safe_error_message


class SemanticSimilarityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    embedding: EmbeddingConfig


class SemanticSimilarity(AsyncMetric):
    name = "semantic_similarity"
    version = "1.0"
    category = MetricCategory.ANSWER_QUALITY
    direction = MetricDirection.HIGHER_IS_BETTER
    score_range = (-1.0, 1.0)
    required_inputs = ("expected_output", "actual_output", "embedding model")
    description = (
        "Cosine similarity between embeddings of the output and the expected output, from the "
        "configured embedding model. Scale depends on the model (many rarely go below 0); only "
        "compare scores from the same embedding model. 0.0 for an empty output."
    )
    Config: ClassVar[type[BaseModel]] = SemanticSimilarityConfig

    def __init__(self, config: Any = None) -> None:
        super().__init__(config)
        self._client: EmbeddingClient | None = None
        self._limit: asyncio.Semaphore | None = None

    @property
    def embedding(self) -> EmbeddingConfig:
        assert isinstance(self.config, SemanticSimilarityConfig)
        return self.config.embedding

    def env_references(self) -> dict[str, str]:
        return {f"embedding.{k}": v for k, v in self.embedding.env_references().items()}

    async def evaluate_async(self, data: MetricInput) -> MetricResult:
        expected = data.case.expected_output
        if expected is None:
            return self.not_applicable("case has no expected_output")
        provenance = {
            "embedding_provider": self.embedding.provider,
            "embedding_model_id": self.embedding.model_id,
        }
        actual = data.response.output_text
        if not actual.strip():
            return self.scored(0.0, empty_output=True, **provenance)
        if self._client is None:
            self._client = build_embedding_client(self.embedding)
        if self._limit is None:
            self._limit = asyncio.Semaphore(self.embedding.max_concurrency)
        try:
            async with self._limit:
                embeddings = await asyncio.wait_for(
                    self._client.embed([expected, actual]), timeout=self.embedding.timeout_seconds
                )
        except TimeoutError:
            return self.error("timeout", "embedding request timed out", **provenance)
        except ProviderError as exc:
            return self.error(str(exc.category), safe_error_message(exc.message), **provenance)
        similarity = cosine_similarity(*embeddings.vectors)
        if similarity is None:
            return self.error("zero_vector", "an embedding had zero length", **provenance)
        return self.scored(
            round(similarity, 6),
            embedding_method=embeddings.method,
            embedding_input_tokens=embeddings.input_tokens,
            **provenance,
        )

    async def aclose(self) -> None:
        self._limit = None
        if self._client is not None:
            client, self._client = self._client, None
            await client.aclose()
