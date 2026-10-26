from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Dataset, DatasetVersion
from app.domain.datasets import EvaluationCase


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    schema_version: Literal["1.0"] = "1.0"
    cases: list[EvaluationCase] = Field(min_length=1)


class DatasetUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class DatasetVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    cases: list[EvaluationCase] = Field(min_length=1)


class DatasetRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None
    current_version: int
    case_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, dataset: Dataset, case_count: int) -> DatasetRead:
        return cls(
            id=dataset.id,
            project_id=dataset.project_id,
            name=dataset.name,
            description=dataset.description,
            current_version=dataset.current_version,
            case_count=case_count,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )


class DatasetVersionRead(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    version_number: int
    schema_version: str
    content_hash: str
    case_count: int
    created_at: datetime

    @classmethod
    def from_model(cls, version: DatasetVersion) -> DatasetVersionRead:
        return cls(
            id=version.id,
            dataset_id=version.dataset_id,
            version_number=version.version_number,
            schema_version=version.schema_version,
            content_hash=version.content_hash,
            case_count=version.case_count,
            created_at=version.created_at,
        )


class DatasetVersionDetail(DatasetVersionRead):
    cases: list[EvaluationCase]
    # Count of cases matching the tag/search filters (pagination applies to ``cases``).
    matching_cases: int
    limit: int
    offset: int
