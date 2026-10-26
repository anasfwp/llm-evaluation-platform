from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.core.errors import InputValidationError
from app.domain.datasets import load_dataset

VALID_CASE = {"case_key": "c1", "input": {"question": "q?"}, "expected_output": "a"}


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _locations(exc: InputValidationError) -> list[str]:
    return [issue.location for issue in exc.issues]


def test_load_json_dataset(tmp_path: Path) -> None:
    doc = {"schema_version": "1.0", "name": "ds", "cases": [VALID_CASE]}
    dataset = load_dataset(_write(tmp_path, "ds.json", json.dumps(doc)))
    assert dataset.name == "ds"
    assert dataset.cases[0].case_key == "c1"
    assert dataset.content_hash().startswith("sha256:")


def test_content_hash_is_stable_and_content_sensitive(tmp_path: Path) -> None:
    doc = {"schema_version": "1.0", "name": "ds", "cases": [VALID_CASE]}
    first = load_dataset(_write(tmp_path, "a.json", json.dumps(doc)))
    second = load_dataset(_write(tmp_path, "b.json", json.dumps(doc, indent=4)))
    doc["cases"][0]["expected_output"] = "changed"
    third = load_dataset(_write(tmp_path, "c.json", json.dumps(doc)))
    assert first.content_hash() == second.content_hash()
    assert first.content_hash() != third.content_hash()


def test_json_validation_reports_case_level_field_paths(tmp_path: Path) -> None:
    doc = {
        "schema_version": "1.0",
        "name": "ds",
        "cases": [VALID_CASE, {"case_key": "c2", "expected_output": "a"}],
    }
    with pytest.raises(InputValidationError) as info:
        load_dataset(_write(tmp_path, "ds.json", json.dumps(doc)))
    assert "cases[1].input" in _locations(info.value)


def test_rejects_unknown_fields_and_schema_version(tmp_path: Path) -> None:
    doc = {"schema_version": "2.0", "name": "ds", "cases": [{**VALID_CASE, "answer": "x"}]}
    with pytest.raises(InputValidationError) as info:
        load_dataset(_write(tmp_path, "ds.json", json.dumps(doc)))
    locations = _locations(info.value)
    assert "schema_version" in locations
    assert "cases[0].answer" in locations


def test_rejects_duplicate_case_keys(tmp_path: Path) -> None:
    doc = {"schema_version": "1.0", "name": "ds", "cases": [VALID_CASE, VALID_CASE]}
    with pytest.raises(InputValidationError, match="duplicate case_key values: c1"):
        load_dataset(_write(tmp_path, "ds.json", json.dumps(doc)))


def test_rejects_empty_dataset_and_invalid_case_key(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError):
        load_dataset(
            _write(tmp_path, "a.json", '{"schema_version": "1.0", "name": "x", "cases": []}')
        )
    bad_key = {**VALID_CASE, "case_key": "has spaces"}
    doc = {"schema_version": "1.0", "name": "ds", "cases": [bad_key]}
    with pytest.raises(InputValidationError) as info:
        load_dataset(_write(tmp_path, "b.json", json.dumps(doc)))
    assert "cases[0].case_key" in _locations(info.value)


def test_invalid_json_reports_position(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError, match="line 1, column"):
        load_dataset(_write(tmp_path, "ds.json", "{not json"))


def test_load_jsonl_dataset_skips_blank_lines(tmp_path: Path) -> None:
    second = {**VALID_CASE, "case_key": "c2"}
    content = json.dumps(VALID_CASE) + "\n\n" + json.dumps(second) + "\n"
    dataset = load_dataset(_write(tmp_path, "my-set.jsonl", content))
    assert dataset.name == "my-set"
    assert [c.case_key for c in dataset.cases] == ["c1", "c2"]


def test_jsonl_errors_report_line_numbers(tmp_path: Path) -> None:
    content = "\n".join([json.dumps(VALID_CASE), "{broken", json.dumps({"case_key": "c3"})])
    with pytest.raises(InputValidationError) as info:
        load_dataset(_write(tmp_path, "ds.jsonl", content))
    locations = _locations(info.value)
    assert "line 2" in locations
    assert "line 3: input" in locations


def test_missing_file_and_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError, match="file not found"):
        load_dataset(tmp_path / "missing.json")
    with pytest.raises(InputValidationError, match="unsupported dataset format"):
        load_dataset(_write(tmp_path, "ds.csv", "a,b"))
