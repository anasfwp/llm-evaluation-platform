from __future__ import annotations

import uuid

from fastapi import APIRouter, Response, status

from app.api.deps import PaginationDep, SessionDep
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services import project_service

router = APIRouter(prefix="/projects", tags=["projects"], responses=ERROR_RESPONSES)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, session: SessionDep) -> ProjectRead:
    return ProjectRead.from_model(project_service.create_project(session, data))


@router.get("")
def list_projects(
    session: SessionDep, page: PaginationDep, include_archived: bool = False
) -> Page[ProjectRead]:
    items, total = project_service.list_projects(
        session, include_archived=include_archived, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[ProjectRead.from_model(p) for p in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, session: SessionDep) -> ProjectRead:
    return ProjectRead.from_model(project_service.get_project(session, project_id))


@router.patch("/{project_id}")
def update_project(project_id: uuid.UUID, data: ProjectUpdate, session: SessionDep) -> ProjectRead:
    return ProjectRead.from_model(project_service.update_project(session, project_id, data))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_project(project_id: uuid.UUID, session: SessionDep) -> Response:
    """Archives the project (soft delete); its runs and results remain retrievable."""
    project_service.archive_project(session, project_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
