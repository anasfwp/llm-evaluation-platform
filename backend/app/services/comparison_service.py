"""Comparisons, named baselines, and saved/inline gate evaluation over persisted runs."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, InvalidRequestError, Issue, NotFoundError
from app.db.models import Baseline, Comparison, EvaluationGate, EvaluationRun
from app.domain.gates import GateConfig, GateResult
from app.domain.runs import RunReport, RunStatus
from app.evaluation.comparison import ComparisonError, compare_runs
from app.evaluation.gates import evaluate_report_gate
from app.schemas.comparison import (
    BaselineCreate,
    BaselineUpdate,
    ComparisonCreate,
    GateCreate,
    GateEvaluate,
    GateUpdate,
)
from app.services.project_service import require_active_project
from app.services.report_service import build_report
from app.services.run_service import get_run


def _completed_run(session: Session, run_id: uuid.UUID, field: str) -> EvaluationRun:
    run = get_run(session, run_id)
    if run.status != RunStatus.COMPLETED:
        raise ConflictError(
            f"run {run_id} is {run.status}; only completed runs can be compared or gated",
            [Issue(field, f"run status is {run.status}")],
        )
    return run


def _report(session: Session, run_id: uuid.UUID, field: str) -> tuple[EvaluationRun, RunReport]:
    run = _completed_run(session, run_id, field)
    return run, build_report(session, run)


# Baselines


def get_baseline(session: Session, baseline_id: uuid.UUID) -> Baseline:
    baseline = session.get(Baseline, baseline_id)
    if baseline is None:
        raise NotFoundError(f"baseline {baseline_id} not found")
    return baseline


def _check_baseline_run(session: Session, project_id: uuid.UUID, run_id: uuid.UUID) -> None:
    run = _completed_run(session, run_id, "run_id")
    if run.project_id != project_id:
        raise InvalidRequestError(
            "the run belongs to another project", [Issue("run_id", "not in this project")]
        )


def _name_taken(
    session: Session,
    model: type[Baseline] | type[EvaluationGate],
    project_id: uuid.UUID,
    name: str,
) -> bool:
    return (
        session.scalar(select(model).where(model.project_id == project_id, model.name == name))
        is not None
    )


def create_baseline(session: Session, project_id: uuid.UUID, data: BaselineCreate) -> Baseline:
    require_active_project(session, project_id)
    if _name_taken(session, Baseline, project_id, data.name):
        raise ConflictError(f"a baseline named '{data.name}' already exists in this project")
    _check_baseline_run(session, project_id, data.run_id)
    baseline = Baseline(
        project_id=project_id, name=data.name, description=data.description, run_id=data.run_id
    )
    session.add(baseline)
    session.commit()
    return baseline


def list_baselines(session: Session, project_id: uuid.UUID) -> list[Baseline]:
    require_active_project(session, project_id)
    return list(
        session.scalars(
            select(Baseline).where(Baseline.project_id == project_id).order_by(Baseline.name)
        )
    )


def update_baseline(session: Session, baseline_id: uuid.UUID, data: BaselineUpdate) -> Baseline:
    baseline = get_baseline(session, baseline_id)
    if data.name is not None and data.name != baseline.name:
        if _name_taken(session, Baseline, baseline.project_id, data.name):
            raise ConflictError(f"a baseline named '{data.name}' already exists in this project")
        baseline.name = data.name
    if "description" in data.model_fields_set:
        baseline.description = data.description
    if data.run_id is not None:
        _check_baseline_run(session, baseline.project_id, data.run_id)
        baseline.run_id = data.run_id
    session.commit()
    return baseline


def delete_baseline(session: Session, baseline_id: uuid.UUID) -> None:
    session.delete(get_baseline(session, baseline_id))
    session.commit()


def _baseline_run_id(
    session: Session, baseline_run_id: uuid.UUID | None, baseline_id: uuid.UUID | None
) -> uuid.UUID | None:
    if baseline_id is not None:
        return get_baseline(session, baseline_id).run_id
    return baseline_run_id


# Comparisons


def create_comparison(session: Session, data: ComparisonCreate) -> Comparison:
    baseline_run_id = _baseline_run_id(session, data.baseline_run_id, data.baseline_id)
    assert baseline_run_id is not None  # guaranteed by ComparisonCreate validation
    baseline_run, baseline = _report(session, baseline_run_id, "baseline_run_id")
    candidate_run, candidate = _report(session, data.candidate_run_id, "candidate_run_id")
    if baseline_run.project_id != candidate_run.project_id:
        raise InvalidRequestError("both runs must belong to the same project")
    try:
        result = compare_runs(baseline, candidate, data.settings)
    except ComparisonError as exc:
        raise InvalidRequestError(str(exc), [Issue("settings.model_pairs", str(exc))]) from None
    row = Comparison(
        project_id=candidate_run.project_id,
        baseline_run_id=baseline_run.id,
        candidate_run_id=candidate_run.id,
        settings_json=data.settings.model_dump(mode="json"),
        summary_json=result.model_dump(mode="json"),
    )
    session.add(row)
    session.commit()
    return row


def get_comparison(session: Session, comparison_id: uuid.UUID) -> Comparison:
    row = session.get(Comparison, comparison_id)
    if row is None:
        raise NotFoundError(f"comparison {comparison_id} not found")
    return row


def list_comparisons(
    session: Session, *, project_id: uuid.UUID | None, limit: int, offset: int
) -> tuple[list[Comparison], int]:
    query = select(Comparison)
    if project_id is not None:
        query = query.where(Comparison.project_id == project_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Comparison.created_at.desc(), Comparison.id).limit(limit).offset(offset)
    )
    return list(rows), total


# Gates


def get_gate(session: Session, gate_id: uuid.UUID) -> EvaluationGate:
    gate = session.get(EvaluationGate, gate_id)
    if gate is None:
        raise NotFoundError(f"gate {gate_id} not found")
    return gate


def gate_config(gate: EvaluationGate) -> GateConfig:
    return GateConfig.model_validate(
        {
            "name": gate.name,
            "missing_metric_policy": gate.missing_metric_policy,
            "rules": gate.rules_json,
        }
    )


def create_gate(session: Session, project_id: uuid.UUID, data: GateCreate) -> EvaluationGate:
    require_active_project(session, project_id)
    if _name_taken(session, EvaluationGate, project_id, data.name):
        raise ConflictError(f"a gate named '{data.name}' already exists in this project")
    gate = EvaluationGate(
        project_id=project_id,
        name=data.name,
        missing_metric_policy=data.missing_metric_policy,
        rules_json=[rule.model_dump(mode="json", exclude_none=True) for rule in data.rules],
    )
    session.add(gate)
    session.commit()
    return gate


def list_gates(session: Session, project_id: uuid.UUID) -> list[EvaluationGate]:
    require_active_project(session, project_id)
    return list(
        session.scalars(
            select(EvaluationGate)
            .where(EvaluationGate.project_id == project_id)
            .order_by(EvaluationGate.name)
        )
    )


def update_gate(session: Session, gate_id: uuid.UUID, data: GateUpdate) -> EvaluationGate:
    gate = get_gate(session, gate_id)
    if data.name is not None and data.name != gate.name:
        if _name_taken(session, EvaluationGate, gate.project_id, data.name):
            raise ConflictError(f"a gate named '{data.name}' already exists in this project")
        gate.name = data.name
    if data.missing_metric_policy is not None:
        gate.missing_metric_policy = data.missing_metric_policy
    if data.rules is not None:
        gate.rules_json = [rule.model_dump(mode="json", exclude_none=True) for rule in data.rules]
    session.commit()
    return gate


def evaluate_gate_request(session: Session, data: GateEvaluate) -> GateResult:
    if data.gate_id is not None:
        saved = get_gate(session, data.gate_id)
        config = gate_config(saved)
    else:
        assert data.rules is not None  # guaranteed by GateEvaluate validation
        saved = None
        config = GateConfig(
            name=data.name, missing_metric_policy=data.missing_metric_policy, rules=data.rules
        )
    run, report = _report(session, data.run_id, "run_id")
    if saved is not None and saved.project_id != run.project_id:
        raise InvalidRequestError("the gate belongs to another project")
    baseline_run_id = _baseline_run_id(session, data.baseline_run_id, data.baseline_id)
    baseline: RunReport | None = None
    if baseline_run_id is not None:
        baseline_run, baseline = _report(session, baseline_run_id, "baseline_run_id")
        if baseline_run.project_id != run.project_id:
            raise InvalidRequestError("the baseline run belongs to another project")
    return evaluate_report_gate(config, report, baseline)
