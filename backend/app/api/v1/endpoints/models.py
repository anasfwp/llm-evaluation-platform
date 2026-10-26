from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.deps import PaginationDep, SessionDep
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.model_config import (
    ConnectivityResult,
    ModelConfigCreate,
    ModelConfigRead,
    ModelConfigUpdate,
)
from app.services import model_config_service

router = APIRouter(tags=["models"], responses=ERROR_RESPONSES)


@router.post("/projects/{project_id}/models", status_code=status.HTTP_201_CREATED)
def create_model_config(
    project_id: uuid.UUID, data: ModelConfigCreate, session: SessionDep
) -> ModelConfigRead:
    config = model_config_service.create_model_config(session, project_id, data)
    return ModelConfigRead.from_model(config)


@router.get("/projects/{project_id}/models")
def list_model_configs(
    project_id: uuid.UUID, session: SessionDep, page: PaginationDep
) -> Page[ModelConfigRead]:
    items, total = model_config_service.list_model_configs(
        session, project_id, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[ModelConfigRead.from_model(m) for m in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/models/{model_config_id}")
def get_model_config(model_config_id: uuid.UUID, session: SessionDep) -> ModelConfigRead:
    return ModelConfigRead.from_model(
        model_config_service.get_model_config(session, model_config_id)
    )


@router.patch("/models/{model_config_id}")
def update_model_config(
    model_config_id: uuid.UUID, data: ModelConfigUpdate, session: SessionDep
) -> ModelConfigRead:
    config = model_config_service.update_model_config(session, model_config_id, data)
    return ModelConfigRead.from_model(config)


@router.post(
    "/models/{model_config_id}/test",
    response_model=ConnectivityResult,
    responses={502: {"model": ConnectivityResult, "description": "Provider call failed"}},
)
def test_model_config(model_config_id: uuid.UUID, session: SessionDep) -> JSONResponse:
    """Send one small probe request to the provider. For paid providers this is billable."""
    config = model_config_service.get_model_config(session, model_config_id)
    result = model_config_service.test_connectivity(config)
    return JSONResponse(status_code=200 if result.ok else 502, content=result.model_dump())
