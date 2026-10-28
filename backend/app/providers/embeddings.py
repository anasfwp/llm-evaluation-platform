"""Embedding clients used by the ``semantic_similarity`` metric.

``fake`` is a deterministic hashed bag-of-words embedding (no network): its
similarity is lexical, so it only demonstrates the pipeline. ``openai`` and
``openai_compatible`` call ``POST {base_url}/embeddings``; the base URL comes
from an operator-chosen environment variable, never from stored config, and
redirects are not followed (same rules as the chat adapters).
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Protocol

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import SECRET_REFERENCE_PATTERN, ProviderErrorCategory
from app.evaluation.normalization import tokenize
from app.providers.base import ProviderError
from app.providers.credentials import read_env
from app.providers.openai_compatible import DEFAULT_BASE_URL_ENV, resolve_base_url, status_error

FAKE_DIMENSIONS = 256
OPENAI_BASE_URL = "https://api.openai.com/v1"


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    provider: Literal["fake", "openai", "openai_compatible"]
    model_id: str = Field(min_length=1, max_length=200)
    secret_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)
    base_url_env: str = Field(default=DEFAULT_BASE_URL_ENV, pattern=SECRET_REFERENCE_PATTERN)
    timeout_seconds: float = Field(default=30, gt=0, le=600)
    max_concurrency: int = Field(default=4, ge=1, le=32)

    def env_references(self) -> dict[str, str]:
        """Environment variables this configuration would read, keyed by config location."""
        if self.provider == "fake":
            return {}
        default = "OPENAI_API_KEY" if self.provider == "openai" else "OPENAI_COMPATIBLE_API_KEY"
        references = {"secret_reference": self.secret_reference or default}
        if self.provider == "openai_compatible":
            references["base_url_env"] = self.base_url_env
        return references


@dataclass(frozen=True)
class Embeddings:
    vectors: list[list[float]]
    input_tokens: int | None
    method: str


class EmbeddingClient(Protocol):
    async def embed(self, texts: list[str]) -> Embeddings: ...

    async def aclose(self) -> None: ...


class FakeEmbeddingClient:
    method: ClassVar[str] = "hashed_bag_of_words"

    async def embed(self, texts: list[str]) -> Embeddings:
        return Embeddings([_hashed_vector(t) for t in texts], input_tokens=None, method=self.method)

    async def aclose(self) -> None:
        return None


def _hashed_vector(text: str) -> list[float]:
    vector = [0.0] * FAKE_DIMENSIONS
    for token in tokenize(text):
        # A stable hash (unlike hash()), so vectors are identical across processes.
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        vector[int.from_bytes(digest, "big") % FAKE_DIMENSIONS] += 1.0
    return vector


class HTTPEmbeddingClient:
    method: ClassVar[str] = "provider_embeddings"

    def __init__(self, config: EmbeddingConfig, client: httpx.AsyncClient | None = None) -> None:
        self._config = config
        references = config.env_references()
        self._api_key = read_env(references["secret_reference"])
        self._error: ProviderError | None = None
        if config.provider == "openai":
            self._base_url: str | None = OPENAI_BASE_URL
            if self._api_key is None:
                self._error = ProviderError(
                    ProviderErrorCategory.AUTHENTICATION_FAILED,
                    f"API key is not configured: set {references['secret_reference']}",
                )
        else:
            self._base_url, self._error = resolve_base_url(config.base_url_env)
        self._client = client or httpx.AsyncClient(follow_redirects=False)

    async def embed(self, texts: list[str]) -> Embeddings:
        if self._error is not None:
            raise self._error
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._config.model_id, "input": texts},
                headers=headers,
                timeout=self._config.timeout_seconds,
            )
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCategory.TIMEOUT, "request timed out") from None
        except httpx.HTTPError as exc:
            raise ProviderError(
                ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                f"could not reach the provider ({type(exc).__name__})",
            ) from None
        if response.status_code >= 400:
            raise status_error(response)
        if response.status_code >= 300:
            raise ProviderError(
                ProviderErrorCategory.INVALID_REQUEST,
                f"provider answered with a redirect (HTTP {response.status_code})",
            )
        return _parse(response, expected=len(texts), method=self.method)

    async def aclose(self) -> None:
        await self._client.aclose()


def _parse(response: httpx.Response, *, expected: int, method: str) -> Embeddings:
    try:
        data: Any = response.json()
        items = sorted(data["data"], key=lambda item: item["index"])
        vectors = [[float(x) for x in item["embedding"]] for item in items]
    except (ValueError, KeyError, TypeError):
        raise ProviderError(
            ProviderErrorCategory.UNKNOWN, "unexpected embeddings response shape"
        ) from None
    if len(vectors) != expected:
        raise ProviderError(ProviderErrorCategory.UNKNOWN, "wrong number of embeddings returned")
    usage = data.get("usage") if isinstance(data, dict) else None
    tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    return Embeddings(vectors, tokens if isinstance(tokens, int) else None, method)


def build_embedding_client(config: EmbeddingConfig) -> EmbeddingClient:
    if config.provider == "fake":
        return FakeEmbeddingClient()
    return HTTPEmbeddingClient(config)


def cosine_similarity(a: list[float], b: list[float]) -> float | None:
    """Cosine of the angle between two vectors; ``None`` if either has zero length."""
    if len(a) != len(b):
        raise ValueError(f"embedding dimensions differ ({len(a)} vs {len(b)})")
    norm = math.sqrt(math.fsum(x * x for x in a)) * math.sqrt(math.fsum(y * y for y in b))
    if norm == 0:
        return None
    return math.fsum(x * y for x, y in zip(a, b, strict=True)) / norm
