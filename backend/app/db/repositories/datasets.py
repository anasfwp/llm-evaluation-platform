from __future__ import annotations

import json
import uuid

from sqlalchemy import String, cast, func, select
from sqlalchemy.orm import Session

from app.db.models import Dataset, DatasetVersion, EvaluationCase
from app.domain import datasets as domain


def get(session: Session, dataset_id: uuid.UUID) -> Dataset | None:
    return session.get(Dataset, dataset_id)


def get_by_name(session: Session, project_id: uuid.UUID, name: str) -> Dataset | None:
    return session.scalar(
        select(Dataset).where(Dataset.project_id == project_id, Dataset.name == name)
    )


def list_for_project(
    session: Session, project_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Dataset], int]:
    query = select(Dataset).where(Dataset.project_id == project_id)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    items = session.scalars(query.order_by(Dataset.name).limit(limit).offset(offset)).all()
    return list(items), total


def add_version(session: Session, dataset: Dataset, content: domain.Dataset) -> DatasetVersion:
    dataset.current_version += 1
    version = DatasetVersion(
        dataset_id=dataset.id,
        version_number=dataset.current_version,
        schema_version=content.schema_version,
        content_hash=content.content_hash(),
        case_count=len(content.cases),
    )
    session.add(version)
    session.flush()
    session.add_all(
        EvaluationCase(
            dataset_version_id=version.id,
            position=position,
            case_key=case.case_key,
            input_json=case.input,
            expected_output=case.expected_output,
            reference_context=case.reference_context,
            retrieved_contexts_json=[c.model_dump(mode="json") for c in case.retrieved_contexts],
            tags_json=case.tags,
            metadata_json=case.metadata,
        )
        for position, case in enumerate(content.cases)
    )
    session.flush()
    return version


def get_version(session: Session, dataset_id: uuid.UUID, number: int) -> DatasetVersion | None:
    return session.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id, DatasetVersion.version_number == number
        )
    )


def get_version_by_id(session: Session, version_id: uuid.UUID) -> DatasetVersion | None:
    return session.get(DatasetVersion, version_id)


def list_versions(session: Session, dataset_id: uuid.UUID) -> list[DatasetVersion]:
    return list(
        session.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.version_number)
        ).all()
    )


def list_cases(
    session: Session,
    version_id: uuid.UUID,
    *,
    tag: str | None = None,
    search: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[EvaluationCase], int]:
    query = select(EvaluationCase).where(EvaluationCase.dataset_version_id == version_id)
    if tag is not None:
        # Match the JSON-encoded tag so "geo" does not match "geography".
        query = query.where(
            cast(EvaluationCase.tags_json, String).contains(json.dumps(tag), autoescape=True)
        )
    if search:
        query = query.where(EvaluationCase.case_key.contains(search, autoescape=True))
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    query = query.order_by(EvaluationCase.position).offset(offset)
    if limit is not None:
        query = query.limit(limit)
    return list(session.scalars(query).all()), total


def to_domain_case(row: EvaluationCase) -> domain.EvaluationCase:
    return domain.EvaluationCase(
        case_key=row.case_key,
        input=row.input_json,
        expected_output=row.expected_output,
        reference_context=row.reference_context,
        retrieved_contexts=[domain.RetrievedContext(**c) for c in row.retrieved_contexts_json],
        tags=row.tags_json,
        metadata=row.metadata_json,
    )


def load_version(session: Session, dataset: Dataset, version: DatasetVersion) -> domain.Dataset:
    rows, _ = list_cases(session, version.id)
    return domain.Dataset(
        schema_version="1.0",
        name=dataset.name,
        description=dataset.description,
        cases=[to_domain_case(row) for row in rows],
    )
