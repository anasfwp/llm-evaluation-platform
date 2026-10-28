"""Text normalization used by comparison metrics. Changing it changes metric semantics,
so any change here requires bumping the versions of the metrics that use it."""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"\w+")


def _is_punctuation(char: str) -> bool:
    return unicodedata.category(char).startswith("P")


def normalize_text(text: str) -> str:
    """NFKC-normalize, casefold, collapse whitespace, and strip surrounding punctuation.

    Internal punctuation is kept, so ``"3.14"`` and ``"U.S."``-style tokens are
    not altered except at the very ends of the string.
    """
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = " ".join(normalized.split())
    start, end = 0, len(normalized)
    while start < end and (_is_punctuation(normalized[start]) or normalized[start].isspace()):
        start += 1
    while end > start and (_is_punctuation(normalized[end - 1]) or normalized[end - 1].isspace()):
        end -= 1
    return normalized[start:end]


def tokenize(text: str) -> list[str]:
    """Word tokens of the normalized text: runs of Unicode letters, digits, and underscores.

    Punctuation, including internal punctuation, separates tokens here, so ``"h2o."``
    and ``"H2O"`` produce the same tokens.
    """
    return _WORD.findall(normalize_text(text))
