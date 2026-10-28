from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, JSONType, Timestamps, UUIDPrimaryKey
from app.utils.time import utc_now


class Comparison(UUIDPrimaryKey, Base):
    """A stored comparison of two completed runs; the full result is a JSON snapshot."""

    __tablename__ = "comparisons"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    baseline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    candidate_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    settings_json: Mapped[dict[str, Any]] = mapped_column()
    summary_json: Mapped[dict[str, Any]] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utc_now, index=True)


class Baseline(UUIDPrimaryKey, Timestamps, Base):
    """A named pointer to a completed run, used for repeated comparisons and relative gates."""

    __tablename__ = "baselines"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)


class EvaluationGate(UUIDPrimaryKey, Timestamps, Base):
    """A saved, reusable gate configuration (the full GateConfig document)."""

    __tablename__ = "evaluation_gates"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    missing_metric_policy: Mapped[str] = mapped_column(String(10))
    rules_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONType)
