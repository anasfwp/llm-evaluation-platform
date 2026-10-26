from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, UUIDPrimaryKey
from app.utils.time import utc_now


class EvaluationRun(UUIDPrimaryKey, Base):
    __tablename__ = "evaluation_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("dataset_versions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), index=True)
    # Everything needed to reproduce the run: models (no secrets), metrics, run settings.
    config_snapshot_json: Mapped[dict[str, Any]] = mapped_column()
    config_hash: Mapped[str] = mapped_column(String(80))
    metric_infos_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
    # Per-model summaries, written when the run reaches a terminal state.
    summary_json: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONType)
    software_version: Mapped[str] = mapped_column(String(40))
    error_message: Mapped[str | None] = mapped_column(Text)
    total_cases: Mapped[int] = mapped_column(Integer)
    completed_cases: Mapped[int] = mapped_column(Integer, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()
