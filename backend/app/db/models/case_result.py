from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JSONType, UUIDPrimaryKey
from app.utils.time import utc_now


class CaseResult(UUIDPrimaryKey, Base):
    __tablename__ = "case_results"
    # One result per (run, model, case): makes persisting a result idempotent.
    __table_args__ = (UniqueConstraint("run_id", "model_name", "case_key"),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), index=True
    )
    case_key: Mapped[str] = mapped_column(String(200), index=True)
    position: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(100), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    model_id: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), index=True)
    tags_json: Mapped[list[str]] = mapped_column(JSONType, default=list)
    input_snapshot_json: Mapped[dict[str, Any]] = mapped_column()
    expected_output_snapshot: Mapped[str | None] = mapped_column(Text)
    actual_output: Mapped[str | None] = mapped_column(Text)
    latency_ms: Mapped[float | None] = mapped_column(Float)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(Integer)
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message_redacted: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column()
    finished_at: Mapped[datetime] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    metrics: Mapped[list[MetricResult]] = relationship(
        back_populates="case_result",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="MetricResult.position",
    )


class MetricResult(UUIDPrimaryKey, Base):
    __tablename__ = "metric_results"

    case_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("case_results.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int] = mapped_column(Integer)
    metric_name: Mapped[str] = mapped_column(String(100), index=True)
    metric_version: Mapped[str] = mapped_column(String(20))
    score: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20))
    details_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(default=utc_now)

    case_result: Mapped[CaseResult] = relationship(back_populates="metrics")
