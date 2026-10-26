from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Project


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    settings: dict[str, Any] | None = None


class ProjectRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    settings: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    @classmethod
    def from_model(cls, project: Project) -> ProjectRead:
        return cls(
            id=project.id,
            name=project.name,
            description=project.description,
            settings=project.settings_json,
            created_at=project.created_at,
            updated_at=project.updated_at,
            archived_at=project.archived_at,
        )
