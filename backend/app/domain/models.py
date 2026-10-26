"""Model/target configuration and the normalized response every adapter returns."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderErrorCategory(StrEnum):
    """Stable internal error categories; provider-specific errors map onto these."""

    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    AUTHENTICATION_FAILED = "authentication_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    INVALID_REQUEST = "invalid_request"
    UNKNOWN = "unknown_error"

    @property
    def is_transient(self) -> bool:
        return self in _TRANSIENT


_TRANSIENT = frozenset(
    {
        ProviderErrorCategory.RATE_LIMITED,
        ProviderErrorCategory.TIMEOUT,
        ProviderErrorCategory.PROVIDER_UNAVAILABLE,
    }
)


class ModelConfigSnapshot(BaseModel):
    """One model/target under evaluation, as recorded in the run snapshot.

    Credentials are never stored here; later providers reference them by
    environment variable name.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
    provider: str = Field(min_length=1)
    model_id: str = Field(min_length=1, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    max_concurrency: int | None = Field(default=None, ge=1, le=64)


class ModelRequest(BaseModel):
    """What an adapter receives for one case. Expected answers are deliberately excluded."""

    model_config = ConfigDict(frozen=True)

    case_key: str
    input_data: dict[str, Any]


class NormalizedModelResponse(BaseModel):
    model_config = ConfigDict(frozen=True, protected_namespaces=())

    output_text: str
    provider: str
    model_id: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
