from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import ModelConfig

# Credentials are referenced by environment-variable name, never sent as values.
from app.domain.models import SECRET_REFERENCE_PATTERN


class ModelConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    name: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._\-]*$")
    provider: str = Field(min_length=1, max_length=50)
    model_id: str = Field(min_length=1, max_length=200)
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    max_concurrency: int | None = Field(default=None, ge=1, le=64)
    secret_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)


class ModelConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    parameters: dict[str, Any] | None = None
    timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    max_concurrency: int | None = Field(default=None, ge=1, le=64)
    secret_reference: str | None = Field(default=None, pattern=SECRET_REFERENCE_PATTERN)


class ModelConfigRead(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    provider: str
    model_id: str
    parameters: dict[str, Any]
    timeout_seconds: float | None
    max_concurrency: int | None
    secret_reference: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, config: ModelConfig) -> ModelConfigRead:
        return cls(
            id=config.id,
            project_id=config.project_id,
            name=config.name,
            provider=config.provider,
            model_id=config.model_id,
            parameters=config.parameters_json,
            timeout_seconds=config.timeout_seconds,
            max_concurrency=config.max_concurrency,
            secret_reference=config.secret_reference,
            created_at=config.created_at,
            updated_at=config.updated_at,
        )


class ConnectivityResult(BaseModel):
    ok: bool
    provider: str
    latency_ms: float | None
    error_code: str | None = None
    error_message: str | None = None
