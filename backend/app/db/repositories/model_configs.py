from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ModelConfig


def get(session: Session, model_config_id: uuid.UUID) -> ModelConfig | None:
    return session.get(ModelConfig, model_config_id)


def get_by_name(session: Session, project_id: uuid.UUID, name: str) -> ModelConfig | None:
    return session.scalar(
        select(ModelConfig).where(ModelConfig.project_id == project_id, ModelConfig.name == name)
    )


def get_many(session: Session, ids: Sequence[uuid.UUID]) -> list[ModelConfig]:
    rows = {m.id: m for m in session.scalars(select(ModelConfig).where(ModelConfig.id.in_(ids)))}
    # Preserve the caller's order: it defines model order in reports.
    return [rows[i] for i in ids if i in rows]


def list_for_project(
    session: Session, project_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[ModelConfig], int]:
    query = select(ModelConfig).where(ModelConfig.project_id == project_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(query.order_by(ModelConfig.name).limit(limit).offset(offset)).all()
    return list(items), total
