from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Project


def get(session: Session, project_id: uuid.UUID) -> Project | None:
    return session.get(Project, project_id)


def get_by_name(session: Session, name: str) -> Project | None:
    return session.scalar(select(Project).where(Project.name == name))


def list_projects(
    session: Session, *, include_archived: bool, limit: int, offset: int
) -> tuple[list[Project], int]:
    query = select(Project)
    if not include_archived:
        query = query.where(Project.archived_at.is_(None))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(
        query.order_by(Project.created_at.desc(), Project.id).limit(limit).offset(offset)
    ).all()
    return list(items), total
