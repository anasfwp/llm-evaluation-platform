from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Response, UploadFile, status

from app.api.deps import PaginationDep, SessionDep, SettingsDep
from app.core.errors import InvalidRequestError
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.dataset import (
    DatasetCreate,
    DatasetRead,
    DatasetUpdate,
    DatasetVersionCreate,
    DatasetVersionDetail,
    DatasetVersionRead,
)
from app.services import dataset_service
from app.services.dataset_service import ExportFormat

router = APIRouter(tags=["datasets"], responses=ERROR_RESPONSES)


@router.post("/projects/{project_id}/datasets", status_code=status.HTTP_201_CREATED)
def create_dataset(
    project_id: uuid.UUID, data: DatasetCreate, session: SessionDep, settings: SettingsDep
) -> DatasetRead:
    dataset = dataset_service.create_dataset(
        session, project_id, data, max_cases=settings.max_cases_per_run
    )
    return DatasetRead.from_model(dataset, len(data.cases))


@router.get("/projects/{project_id}/datasets")
def list_datasets(
    project_id: uuid.UUID, session: SessionDep, page: PaginationDep
) -> Page[DatasetRead]:
    items, total = dataset_service.list_datasets(
        session, project_id, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[
            DatasetRead.from_model(d, dataset_service.current_case_count(session, d)) for d in items
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post("/datasets/import", status_code=status.HTTP_201_CREATED)
def import_dataset(
    session: SessionDep,
    settings: SettingsDep,
    project_id: Annotated[uuid.UUID, Form()],
    file: Annotated[UploadFile, File(description="A .json or .jsonl dataset file")],
    name: Annotated[str | None, Form(min_length=1, max_length=200)] = None,
) -> DatasetRead:
    content = file.file.read(settings.max_request_bytes + 1)
    if len(content) > settings.max_request_bytes:
        raise InvalidRequestError(f"file exceeds {settings.max_request_bytes} bytes")
    dataset = dataset_service.import_dataset(
        session,
        project_id,
        filename=file.filename or "upload.json",
        content=content,
        name=name,
        max_cases=settings.max_cases_per_run,
    )
    return DatasetRead.from_model(dataset, dataset_service.current_case_count(session, dataset))


@router.get("/datasets/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, session: SessionDep) -> DatasetRead:
    dataset = dataset_service.get_dataset(session, dataset_id)
    return DatasetRead.from_model(dataset, dataset_service.current_case_count(session, dataset))


@router.patch("/datasets/{dataset_id}")
def update_dataset(dataset_id: uuid.UUID, data: DatasetUpdate, session: SessionDep) -> DatasetRead:
    dataset = dataset_service.update_dataset(session, dataset_id, data)
    return DatasetRead.from_model(dataset, dataset_service.current_case_count(session, dataset))


@router.post("/datasets/{dataset_id}/versions", status_code=status.HTTP_201_CREATED)
def create_version(
    dataset_id: uuid.UUID,
    data: DatasetVersionCreate,
    session: SessionDep,
    settings: SettingsDep,
) -> DatasetVersionRead:
    version = dataset_service.add_version(
        session, dataset_id, data, max_cases=settings.max_cases_per_run
    )
    return DatasetVersionRead.from_model(version)


@router.get("/datasets/{dataset_id}/versions")
def list_versions(dataset_id: uuid.UUID, session: SessionDep) -> list[DatasetVersionRead]:
    return [
        DatasetVersionRead.from_model(v) for v in dataset_service.list_versions(session, dataset_id)
    ]


@router.get("/datasets/{dataset_id}/versions/{version}")
def get_version(
    dataset_id: uuid.UUID,
    version: int,
    session: SessionDep,
    page: PaginationDep,
    tag: str | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Search case keys")] = None,
) -> DatasetVersionDetail:
    selected = dataset_service.get_version(session, dataset_id, version)
    cases, matching = dataset_service.list_version_cases(
        session, selected, tag=tag, search=q, limit=page.limit, offset=page.offset
    )
    return DatasetVersionDetail(
        **DatasetVersionRead.from_model(selected).model_dump(),
        cases=cases,
        matching_cases=matching,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/datasets/{dataset_id}/export")
def export_dataset(
    dataset_id: uuid.UUID,
    session: SessionDep,
    format: ExportFormat = "jsonl",
    version: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    content, media_type, filename = dataset_service.export_dataset(
        session, dataset_id, version=version, fmt=format
    )
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
