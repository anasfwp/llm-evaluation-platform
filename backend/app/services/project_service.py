from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.db.models import Project
from app.db.repositories import projects as repo
from app.schemas.project import ProjectCreate, ProjectUpdate
from app.utils.time import utc_now


def get_project(session: Session, project_id: uuid.UUID) -> Project:
    project = repo.get(session, project_id)
    if project is None:
        raise NotFoundError(f"project {project_id} not found")
    return project


def require_active_project(session: Session, project_id: uuid.UUID) -> Project:
    project = get_project(session, project_id)
    if project.archived_at is not None:
        raise ConflictError(f"project {project_id} is archived")
    return project


def create_project(session: Session, data: ProjectCreate) -> Project:
    if repo.get_by_name(session, data.name) is not None:
        raise ConflictError(f"a project named '{data.name}' already exists")
    project = Project(name=data.name, description=data.description, settings_json=data.settings)
    session.add(project)
    session.commit()
    return project


def list_projects(
    session: Session, *, include_archived: bool, limit: int, offset: int
) -> tuple[list[Project], int]:
    return repo.list_projects(
        session, include_archived=include_archived, limit=limit, offset=offset
    )


def update_project(session: Session, project_id: uuid.UUID, data: ProjectUpdate) -> Project:
    project = require_active_project(session, project_id)
    if data.name is not None and data.name != project.name:
        if repo.get_by_name(session, data.name) is not None:
            raise ConflictError(f"a project named '{data.name}' already exists")
        project.name = data.name
    if "description" in data.model_fields_set:
        project.description = data.description
    if data.settings is not None:
        project.settings_json = data.settings
    session.commit()
    return project


def archive_project(session: Session, project_id: uuid.UUID) -> None:
    """Archive rather than delete: runs and results stay available for audit."""
    project = get_project(session, project_id)
    if project.archived_at is None:
        project.archived_at = utc_now()
        session.commit()
