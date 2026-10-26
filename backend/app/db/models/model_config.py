from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey


class ModelConfig(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "model_configs"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    provider: Mapped[str] = mapped_column(String(50))
    model_id: Mapped[str] = mapped_column(String(200))
    parameters_json: Mapped[dict[str, Any]] = mapped_column(default=dict)
    timeout_seconds: Mapped[float | None] = mapped_column(Float)
    max_concurrency: Mapped[int | None] = mapped_column(Integer)
    # Name of the environment variable / secret holding the credential, never the value.
    secret_reference: Mapped[str | None] = mapped_column(String(100))
