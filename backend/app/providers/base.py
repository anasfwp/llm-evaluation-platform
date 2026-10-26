"""Provider adapter contract.

Adapters hide provider SDK/HTTP details and translate failures into
``ProviderError`` with a stable ``ProviderErrorCategory``. They never write
to storage and never decide run aggregation or gate policy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Protocol, Self

from pydantic import BaseModel

from app.domain.datasets import Dataset
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)


class ProviderError(Exception):
    def __init__(self, category: ProviderErrorCategory, message: str) -> None:
        self.category = category
        self.message = message
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
