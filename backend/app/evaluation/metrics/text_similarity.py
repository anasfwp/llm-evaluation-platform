from __future__ import annotations

from collections import Counter

from app.domain.metrics import MetricCategory, MetricDirection, MetricResult
from app.evaluation.metrics.base import Metric, MetricInput
from app.evaluation.normalization import tokenize


def token_f1(expected: str, actual: str) -> tuple[float, float, float]:
    """Return ``(precision, recall, f1)`` over multisets of normalized word tokens."""
    expected_tokens, actual_tokens = tokenize(expected), tokenize(actual)
    if not expected_tokens and not actual_tokens:
        return 1.0, 1.0, 1.0
    if not expected_tokens or not actual_tokens:
        return 0.0, 0.0, 0.0
    overlap = sum((Counter(expected_tokens) & Counter(actual_tokens)).values())
    if overlap == 0:
        return 0.0, 0.0, 0.0
    precision = overlap / len(actual_tokens)
    recall = overlap / len(expected_tokens)
    return precision, recall, 2 * precision * recall / (precision + recall)


class TokenF1(Metric):
    name = "token_f1"
    version = "1.0"
    category = MetricCategory.ANSWER_QUALITY
    direction = MetricDirection.HIGHER_IS_BETTER
    score_range = (0.0, 1.0)
    required_inputs = ("expected_output", "actual_output")
    description = (
        "Harmonic mean of token precision and recall between the output and the expected "
        "output, over normalized word tokens (SQuAD-style, without English article removal). "
        "Lexical overlap only: paraphrases score low and wrong answers sharing words score high."
    )

    def evaluate(self, data: MetricInput) -> MetricResult:
        expected = data.case.expected_output
        if expected is None:
            return self.not_applicable("case has no expected_output")
        precision, recall, f1 = token_f1(expected, data.response.output_text)
        return self.scored(round(f1, 6), precision=round(precision, 6), recall=round(recall, 6))
