from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, Timestamps, UUIDPrimaryKey
from app.utils.time import utc_now


class Dataset(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "datasets"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    current_version: Mapped[int] = mapped_column(Integer, default=0)


class DatasetVersion(UUIDPrimaryKey, Base):
    """Immutable snapshot of a dataset's cases; runs reference a version, never the dataset."""

    __tablename__ = "dataset_versions"
    __table_args__ = (UniqueConstraint("dataset_id", "version_number"),)

    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    schema_version: Mapped[str] = mapped_column(String(10))
    content_hash: Mapped[str] = mapped_column(String(80))
    case_count: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)


class EvaluationCase(UUIDPrimaryKey, Base):
    __tablename__ = "evaluation_cases"
    __table_args__ = (UniqueConstraint("dataset_version_id", "case_key"),)

    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    case_key: Mapped[str] = mapped_column(String(200), index=True)
    input_json: Mapped[dict[str, Any]] = mapped_column()
    expected_output: Mapped[str | None] = mapped_column(Text)
    reference_context: Mapped[str | None] = mapped_column(Text)
    retrieved_contexts_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType, default=list)
    tags_json: Mapped[list[str]] = mapped_column(JSONType, default=list)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
