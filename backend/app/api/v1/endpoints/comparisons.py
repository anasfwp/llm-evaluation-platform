from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Response, status

from app.api.deps import PaginationDep, SessionDep
from app.domain.comparison import RunComparison
from app.domain.gates import GateResult
from app.evaluation.reporting import render_comparison_markdown
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.comparison import (
    BaselineCreate,
    BaselineRead,
    BaselineUpdate,
    ComparisonCreate,
    ComparisonListItem,
    ComparisonRead,
    GateCreate,
    GateEvaluate,
    GateRead,
    GateUpdate,
)
from app.services import comparison_service as service

router = APIRouter(responses=ERROR_RESPONSES)


@router.post("/comparisons", status_code=status.HTTP_201_CREATED, tags=["comparisons"])
def create_comparison(data: ComparisonCreate, session: SessionDep) -> ComparisonRead:
    """Compare a completed candidate run with a completed baseline run (or saved baseline)."""
    return ComparisonRead.from_model(service.create_comparison(session, data))


@router.get("/comparisons", tags=["comparisons"])
def list_comparisons(
    session: SessionDep, page: PaginationDep, project_id: uuid.UUID | None = None
) -> Page[ComparisonListItem]:
    rows, total = service.list_comparisons(
        session, project_id=project_id, limit=page.limit, offset=page.offset
    )
    return Page(
        items=[ComparisonListItem.from_model(r) for r in rows],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/comparisons/{comparison_id}", tags=["comparisons"])
def get_comparison(comparison_id: uuid.UUID, session: SessionDep) -> ComparisonRead:
    return ComparisonRead.from_model(service.get_comparison(session, comparison_id))


@router.get("/comparisons/{comparison_id}/report", tags=["comparisons"])
def export_comparison(
    comparison_id: uuid.UUID,
    session: SessionDep,
    format: Literal["json", "markdown"] = "markdown",
) -> Response:
    row = service.get_comparison(session, comparison_id)
    result = RunComparison.model_validate(row.summary_json)
    stem = f"comparison-{row.id}"
    if format == "json":
        content, media_type, filename = result.model_dump_json(indent=2), "application/json", stem
        filename += ".json"
    else:
        content, media_type = render_comparison_markdown(result), "text/markdown"
        filename = f"{stem}.md"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post(
    "/projects/{project_id}/baselines", status_code=status.HTTP_201_CREATED, tags=["baselines"]
)
def create_baseline(
    project_id: uuid.UUID, data: BaselineCreate, session: SessionDep
) -> BaselineRead:
    return BaselineRead.from_model(service.create_baseline(session, project_id, data))


@router.get("/projects/{project_id}/baselines", tags=["baselines"])
def list_baselines(project_id: uuid.UUID, session: SessionDep) -> list[BaselineRead]:
    return [BaselineRead.from_model(b) for b in service.list_baselines(session, project_id)]


@router.get("/baselines/{baseline_id}", tags=["baselines"])
def get_baseline(baseline_id: uuid.UUID, session: SessionDep) -> BaselineRead:
    return BaselineRead.from_model(service.get_baseline(session, baseline_id))


@router.patch("/baselines/{baseline_id}", tags=["baselines"])
def update_baseline(
    baseline_id: uuid.UUID, data: BaselineUpdate, session: SessionDep
) -> BaselineRead:
    return BaselineRead.from_model(service.update_baseline(session, baseline_id, data))


@router.delete(
    "/baselines/{baseline_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["baselines"]
)
def delete_baseline(baseline_id: uuid.UUID, session: SessionDep) -> Response:
    """Deletes only the named pointer; the run it referenced is kept."""
    service.delete_baseline(session, baseline_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/projects/{project_id}/gates", status_code=status.HTTP_201_CREATED, tags=["gates"])
def create_gate(project_id: uuid.UUID, data: GateCreate, session: SessionDep) -> GateRead:
    return GateRead.from_model(service.create_gate(session, project_id, data))


@router.get("/projects/{project_id}/gates", tags=["gates"])
def list_gates(project_id: uuid.UUID, session: SessionDep) -> list[GateRead]:
    return [GateRead.from_model(g) for g in service.list_gates(session, project_id)]


@router.get("/gates/{gate_id}", tags=["gates"])
def get_gate(gate_id: uuid.UUID, session: SessionDep) -> GateRead:
    return GateRead.from_model(service.get_gate(session, gate_id))


@router.patch("/gates/{gate_id}", tags=["gates"])
def update_gate(gate_id: uuid.UUID, data: GateUpdate, session: SessionDep) -> GateRead:
    return GateRead.from_model(service.update_gate(session, gate_id, data))


@router.post("/gates/evaluate", tags=["gates"])
def evaluate_gate(data: GateEvaluate, session: SessionDep) -> GateResult:
    """Evaluate a saved gate or inline rules against a completed run.

    Relative rules need ``baseline_run_id`` or ``baseline_id``; without one they fall
    under the missing-metric policy. ``passed`` is false if any rule failed.
    """
    return service.evaluate_gate_request(session, data)
