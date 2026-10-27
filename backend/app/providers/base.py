"""Provider adapter contract.

Adapters hide provider SDK/HTTP details and translate failures into
``ProviderError`` with a stable ``ProviderErrorCategory``. They never write
to storage and never decide run aggregation or gate policy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any, ClassVar, Protocol, Self

from pydantic import BaseModel

from app.domain.datasets import Dataset
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)


class ProviderError(Exception):
    def __init__(
        self,
        category: ProviderErrorCategory,
        message: str,
        *,
        retry_after_seconds: float | None = None,
    ) -> None:
        self.category = category
        self.message = message
        # Server-suggested wait before retrying (e.g. a Retry-After header), when known.
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"{category}: {message}")


class ModelAdapter(Protocol):
    """What the engine needs from an adapter: one normalized call per case."""

    async def generate(
        self,
        *,
        request: ModelRequest,
        model_config: ModelConfigSnapshot,
        timeout_seconds: float,
    ) -> NormalizedModelResponse: ...


class BaseProvider(ABC):
    """A registered provider: validates its parameters and builds an adapter per model config."""

    provider_name: ClassVar[str]
    Parameters: ClassVar[type[BaseModel]]
    # Environment variable read for the credential when ``secret_reference`` is unset.
    default_secret_env: ClassVar[str | None] = None

    @classmethod
    @abstractmethod
    def from_config(cls, model_config: ModelConfigSnapshot, *, dataset: Dataset) -> Self: ...

    @abstractmethod
    async def generate(
        self,
        *,
        request: ModelRequest,
        model_config: ModelConfigSnapshot,
        timeout_seconds: float,
    ) -> NormalizedModelResponse: ...

    async def aclose(self) -> None:  # noqa: B027 - optional hook, no-op by default
        """Release network resources. Called by the engine once a model's cases are done."""

    @classmethod
    def env_references(
        cls, parameters: Mapping[str, Any], secret_reference: str | None
    ) -> dict[str, str]:
        """Environment variables this configuration would read, keyed by config location.

        The API checks these against an operator allowlist so that a model
        configuration cannot make the worker read (and send) arbitrary
        environment variables such as the database URL.
        """
        name = secret_reference or cls.default_secret_env
        return {"secret_reference": name} if name else {}
