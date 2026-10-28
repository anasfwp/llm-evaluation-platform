"""Evaluation dataset schema (version 1.0) and JSON/JSONL loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.errors import InputValidationError, Issue, issues_from_validation_error

DATASET_SCHEMA_VERSION = "1.0"
_OPTIONAL_LATER_FIELDS = ("relevant_document_ids",)


class RetrievedContext(BaseModel):
    """A context chunk retrieved for a case, in rank order (used by retrieval and RAG metrics)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1, max_length=500)
    text: str
    score: float | None = None


class EvaluationCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Stable across dataset versions so results from different runs can be aligned.
    case_key: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:\-]*$")
    input: dict[str, Any] = Field(min_length=1)
    expected_output: str | None = None
    reference_context: str | None = None
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    # Ground-truth relevance labels for retrieval metrics. ``None`` means "not labelled",
    # which makes retrieval metrics not applicable; it is never read as "nothing relevant".
    relevant_document_ids: list[str] | None = Field(default=None, max_length=1000)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Dataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"]
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    cases: list[EvaluationCase] = Field(min_length=1)

    @model_validator(mode="after")
    def _case_keys_unique(self) -> Dataset:
        seen: set[str] = set()
        duplicates: list[str] = []
        for case in self.cases:
            if case.case_key in seen and case.case_key not in duplicates:
                duplicates.append(case.case_key)
            seen.add(case.case_key)
        if duplicates:
            raise ValueError(f"duplicate case_key values: {', '.join(duplicates)}")
        return self

    def content_hash(self) -> str:
        """Hash of the canonical dataset content, recorded in reports for reproducibility."""
        content = self.model_dump(mode="json")
        for case in content["cases"]:
            # Optional fields added after schema 1.0 shipped are left out while unset, so
            # datasets that do not use them keep the hash they had before the field existed.
            for field in _OPTIONAL_LATER_FIELDS:
                if case.get(field) is None:
                    case.pop(field, None)
        canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_dataset(path: Path) -> Dataset:
    """Load a ``.json`` dataset document or a ``.jsonl`` file with one case per line."""
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputValidationError(source, [Issue("", "file not found")]) from None
    except OSError as exc:
        raise InputValidationError(source, [Issue("", f"cannot read file: {exc}")]) from None

    return parse_dataset_text(text, suffix=path.suffix, source=source, name=path.stem)


def parse_dataset_text(text: str, *, suffix: str, source: str, name: str) -> Dataset:
    """Parse dataset content by file suffix. ``name`` is used for JSONL (which has no header)."""
    suffix = suffix.lower()
    if suffix == ".json":
        return _parse_json_dataset(source, text)
    if suffix == ".jsonl":
        return _parse_jsonl_dataset(source, text, name=name)
    raise InputValidationError(
        source, [Issue("", f"unsupported dataset format '{suffix}'; use .json or .jsonl")]
    )


def dataset_to_jsonl(dataset: Dataset) -> str:
    return "".join(case.model_dump_json() + "\n" for case in dataset.cases)


def _parse_json_dataset(source: str, text: str) -> Dataset:
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        issue = Issue(f"line {exc.lineno}, column {exc.colno}", f"invalid JSON: {exc.msg}")
        raise InputValidationError(source, [issue]) from None
    try:
        return Dataset.model_validate(raw)
    except ValidationError as exc:
        raise InputValidationError(source, issues_from_validation_error(exc)) from None


def _parse_jsonl_dataset(source: str, text: str, *, name: str) -> Dataset:
    cases: list[EvaluationCase] = []
    issues: list[Issue] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        prefix = f"line {line_number}"
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            issues.append(Issue(prefix, f"invalid JSON: {exc.msg}"))
            continue
        try:
            cases.append(EvaluationCase.model_validate(raw))
        except ValidationError as exc:
            issues.extend(
                Issue(f"{prefix}: {issue.location}" if issue.location else prefix, issue.message)
                for issue in issues_from_validation_error(exc)
            )
    if issues:
        raise InputValidationError(source, issues)
    try:
        return Dataset(schema_version=DATASET_SCHEMA_VERSION, name=name, cases=cases)
    except ValidationError as exc:
        raise InputValidationError(source, issues_from_validation_error(exc)) from None
