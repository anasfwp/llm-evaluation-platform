from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from pathlib import PurePath
from typing import Literal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import (
    ConflictError,
    InputValidationError,
    InvalidRequestError,
    Issue,
    NotFoundError,
    issues_from_validation_error,
)
from app.db.models import Dataset, DatasetVersion
from app.db.repositories import datasets as repo
from app.domain import datasets as domain
from app.schemas.dataset import DatasetCreate, DatasetUpdate, DatasetVersionCreate
from app.services.project_service import require_active_project

ExportFormat = Literal["json", "jsonl"]


def _build(
    name: str,
    description: str | None,
    cases: Sequence[domain.EvaluationCase],
    *,
    max_cases: int,
) -> domain.Dataset:
    if len(cases) > max_cases:
        raise InvalidRequestError(
            f"dataset has {len(cases)} cases; the limit is {max_cases}",
            [Issue("cases", f"at most {max_cases} cases allowed")],
        )
    try:
        return domain.Dataset(
            schema_version="1.0", name=name, description=description, cases=list(cases)
        )
    except ValidationError as exc:
        raise InvalidRequestError(
            "the dataset contains invalid cases", issues_from_validation_error(exc)
        ) from None


def _create(session: Session, project_id: uuid.UUID, content: domain.Dataset) -> Dataset:
    require_active_project(session, project_id)
    if repo.get_by_name(session, project_id, content.name) is not None:
        raise ConflictError(f"a dataset named '{content.name}' already exists in this project")
    dataset = Dataset(project_id=project_id, name=content.name, description=content.description)
    session.add(dataset)
    session.flush()
    repo.add_version(session, dataset, content)
    session.commit()
    return dataset


def create_dataset(
    session: Session, project_id: uuid.UUID, data: DatasetCreate, *, max_cases: int
) -> Dataset:
    content = _build(data.name, data.description, data.cases, max_cases=max_cases)
    return _create(session, project_id, content)


def import_dataset(
    session: Session,
    project_id: uuid.UUID,
    *,
    filename: str,
    content: bytes,
    name: str | None,
    max_cases: int,
) -> Dataset:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InvalidRequestError("the uploaded file is not valid UTF-8") from None
    path = PurePath(filename)
    try:
        parsed = domain.parse_dataset_text(
            text, suffix=path.suffix, source=path.name, name=name or path.stem
        )
    except InputValidationError as exc:
        raise InvalidRequestError(
            f"the uploaded dataset '{path.name}' is invalid", exc.issues
        ) from None
    built = _build(name or parsed.name, parsed.description, parsed.cases, max_cases=max_cases)
    return _create(session, project_id, built)


def get_dataset(session: Session, dataset_id: uuid.UUID) -> Dataset:
    dataset = repo.get(session, dataset_id)
    if dataset is None:
        raise NotFoundError(f"dataset {dataset_id} not found")
    return dataset


def current_case_count(session: Session, dataset: Dataset) -> int:
    version = repo.get_version(session, dataset.id, dataset.current_version)
    return version.case_count if version is not None else 0


def list_datasets(
    session: Session, project_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Dataset], int]:
    require_active_project(session, project_id)
    return repo.list_for_project(session, project_id, limit=limit, offset=offset)


def update_dataset(session: Session, dataset_id: uuid.UUID, data: DatasetUpdate) -> Dataset:
    dataset = get_dataset(session, dataset_id)
    if data.name is not None and data.name != dataset.name:
        if repo.get_by_name(session, dataset.project_id, data.name) is not None:
            raise ConflictError(f"a dataset named '{data.name}' already exists in this project")
        dataset.name = data.name
    if "description" in data.model_fields_set:
        dataset.description = data.description
    session.commit()
    return dataset


def add_version(
    session: Session, dataset_id: uuid.UUID, data: DatasetVersionCreate, *, max_cases: int
) -> DatasetVersion:
    dataset = get_dataset(session, dataset_id)
    content = _build(dataset.name, dataset.description, data.cases, max_cases=max_cases)
    version = repo.add_version(session, dataset, content)
    session.commit()
    return version


def list_versions(session: Session, dataset_id: uuid.UUID) -> list[DatasetVersion]:
    get_dataset(session, dataset_id)
    return repo.list_versions(session, dataset_id)


def get_version(session: Session, dataset_id: uuid.UUID, number: int) -> DatasetVersion:
    get_dataset(session, dataset_id)
    version = repo.get_version(session, dataset_id, number)
    if version is None:
        raise NotFoundError(f"dataset {dataset_id} has no version {number}")
    return version


def list_version_cases(
    session: Session,
    version: DatasetVersion,
    *,
    tag: str | None,
    search: str | None,
    limit: int,
    offset: int,
) -> tuple[list[domain.EvaluationCase], int]:
    rows, total = repo.list_cases(
        session, version.id, tag=tag, search=search, limit=limit, offset=offset
    )
    return [repo.to_domain_case(row) for row in rows], total


def export_dataset(
    session: Session, dataset_id: uuid.UUID, *, version: int | None, fmt: ExportFormat
) -> tuple[str, str, str]:
    """Return ``(content, media_type, filename)``."""
    dataset = get_dataset(session, dataset_id)
    selected = get_version(session, dataset_id, version or dataset.current_version)
    content = repo.load_version(session, dataset, selected)
    stem = f"{dataset.name}-v{selected.version_number}"
    if fmt == "jsonl":
        return domain.dataset_to_jsonl(content), "application/x-ndjson", f"{stem}.jsonl"
    body = json.dumps(content.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
    return body, "application/json", f"{stem}.json"
