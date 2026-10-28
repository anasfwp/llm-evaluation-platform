"""Retrieval quality metrics over a case's ranked ``retrieved_contexts``.

They need explicit relevance labels (``relevant_document_ids``) and compare
document IDs only, never text. Duplicate IDs in the ranking count once, at
their best rank.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, ConfigDict, Field

from app.domain.datasets import EvaluationCase
from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.evaluation.metrics.base import Metric, MetricInput


class TopKConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    k: int = Field(default=5, ge=1, le=1000)


class RankConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Only the first k results count; unset means the whole ranking.
    k: int | None = Field(default=None, ge=1, le=1000)


def _ranking(case: EvaluationCase) -> list[str]:
    seen: set[str] = set()
    ranked: list[str] = []
    for context in case.retrieved_contexts:
        if context.document_id not in seen:
            seen.add(context.document_id)
            ranked.append(context.document_id)
    return ranked


class _RetrievalMetric(Metric):
    category = MetricCategory.RETRIEVAL_QUALITY
    direction = MetricDirection.HIGHER_IS_BETTER
    score_range = (0.0, 1.0)
    required_inputs = ("retrieved_contexts", "relevant_document_ids")

    def _labels(self, case: EvaluationCase) -> tuple[list[str], set[str]] | MetricResult:
        """The deduplicated ranking and relevant set, or a not-applicable result."""
        if case.relevant_document_ids is None:
            return self.not_applicable("case has no relevant_document_ids labels")
        return _ranking(case), set(case.relevant_document_ids)


class RetrievalPrecisionAtK(_RetrievalMetric):
    name = "retrieval_precision_at_k"
    version = "1.0"
    description = (
        "Share of the top-k retrieved documents that are labelled relevant: "
        "|relevant ∩ top_k| / |top_k|, where |top_k| = min(k, retrieved). "
        "Not applicable without relevance labels or when nothing was retrieved."
    )
    Config: ClassVar[type[BaseModel]] = TopKConfig

    def evaluate(self, data: MetricInput) -> MetricResult:
        labels = self._labels(data.case)
        if isinstance(labels, MetricResult):
            return labels
        ranking, relevant = labels
        if not ranking:
            return self.not_applicable("no retrieved_contexts to score")
        assert isinstance(self.config, TopKConfig)
        top = ranking[: self.config.k]
        hits = [doc for doc in top if doc in relevant]
        return self.scored(
            round(len(hits) / len(top), 6), k=self.config.k, k_effective=len(top), hits=hits
        )


class RetrievalRecallAtK(_RetrievalMetric):
    name = "retrieval_recall_at_k"
    version = "1.0"
    description = (
        "Share of the labelled relevant documents found in the top-k retrieved: "
        "|relevant ∩ top_k| / |relevant|. 0.0 when nothing was retrieved. Not applicable "
        "without relevance labels or when the label set is empty (recall is undefined)."
    )
    Config: ClassVar[type[BaseModel]] = TopKConfig

    def evaluate(self, data: MetricInput) -> MetricResult:
        labels = self._labels(data.case)
        if isinstance(labels, MetricResult):
            return labels
        ranking, relevant = labels
        if not relevant:
            return self.not_applicable("relevant_document_ids is empty; recall is undefined")
        assert isinstance(self.config, TopKConfig)
        top = ranking[: self.config.k]
        hits = [doc for doc in top if doc in relevant]
        missed = sorted(relevant - set(hits))
        return self.scored(
            round(len(hits) / len(relevant), 6), k=self.config.k, hits=hits, missed=missed
        )


class ReciprocalRank(_RetrievalMetric):
    name = "reciprocal_rank"
    version = "1.0"
    description = (
        "1 / rank of the first relevant document in the retrieved ranking (optionally only "
        "the top k), 0.0 if none is relevant. Its mean over cases is the MRR. Not applicable "
        "without relevance labels or when the label set is empty."
    )
    Config: ClassVar[type[BaseModel]] = RankConfig

    def evaluate(self, data: MetricInput) -> MetricResult:
        labels = self._labels(data.case)
        if isinstance(labels, MetricResult):
            return labels
        ranking, relevant = labels
        if not relevant:
            return self.not_applicable("relevant_document_ids is empty; nothing can be found")
        assert isinstance(self.config, RankConfig)
        considered = ranking if self.config.k is None else ranking[: self.config.k]
        for rank, doc in enumerate(considered, start=1):
            if doc in relevant:
                return self.scored(round(1 / rank, 6), first_relevant_rank=rank, document_id=doc)
        return self.scored(0.0, first_relevant_rank=None, k=self.config.k)
