from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from app.core.errors import InputValidationError
from app.evaluation.loader import load_config

DATASET = {
    "schema_version": "1.0",
    "name": "ds",
    "cases": [
        {"case_key": "c1", "input": {"q": "a"}, "expected_output": "x"},
        {"case_key": "c2", "input": {"q": "b"}, "expected_output": "y"},
    ],
}


def _config(**overrides: Any) -> dict[str, Any]:
    config: dict[str, Any] = {
        "project": "p",
        "dataset": "data/ds.json",
        "models": [{"name": "m1", "provider": "fake", "model_id": "f"}],
        "metrics": [{"name": "exact_match"}],
    }
    config.update(overrides)
    return config


def _setup(tmp_path: Path, config: dict[str, Any]) -> Path:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "ds.json").write_text(json.dumps(DATASET), encoding="utf-8")
    path = tmp_path / "eval.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def _issues(tmp_path: Path, config: dict[str, Any]) -> list[str]:
    with pytest.raises(InputValidationError) as info:
        load_config(_setup(tmp_path, config))
    return [str(issue) for issue in info.value.issues]


def test_valid_config_resolves_dataset_relative_to_config_file(tmp_path: Path) -> None:
    loaded = load_config(_setup(tmp_path, _config()))
    assert loaded.dataset_path == tmp_path / "data" / "ds.json"
    assert len(loaded.dataset.cases) == 2
    assert [m.name for m in loaded.metrics] == ["exact_match"]
    assert loaded.gate is None


def test_unknown_keys_are_rejected(tmp_path: Path) -> None:
    issues = _issues(tmp_path, _config(temperature=0))
    assert any(issue.startswith("temperature:") for issue in issues)


def test_unknown_provider_is_located(tmp_path: Path) -> None:
    models = [{"name": "m1", "provider": "no-such-provider", "model_id": "x"}]
    issues = _issues(tmp_path, _config(models=models))
    expected = "models[0].provider: unknown provider 'no-such-provider'"
    assert any(i.startswith(expected) for i in issues)


def test_invalid_provider_parameters_are_located(tmp_path: Path) -> None:
    models = [{"name": "m1", "provider": "fake", "model_id": "x", "parameters": {"mode": "zz"}}]
    issues = _issues(tmp_path, _config(models=models))
    assert any(i.startswith("models[0].parameters.mode") for i in issues)


def test_unknown_metric_version_and_config(tmp_path: Path) -> None:
    metrics = [
        {"name": "bleu"},
        {"name": "exact_match", "version": "9.9"},
        {"name": "latency", "config": {"x": 1}},
    ]
    issues = _issues(tmp_path, _config(metrics=metrics))
    assert any(i.startswith("metrics[0]: unknown metric 'bleu'") for i in issues)
    assert any(i.startswith("metrics[1]:") and "9.9" in i for i in issues)
    assert any(i.startswith("metrics[2].config.x") for i in issues)


def test_duplicate_model_names_rejected(tmp_path: Path) -> None:
    model = {"name": "m1", "provider": "fake", "model_id": "f"}
    issues = _issues(tmp_path, _config(models=[model, model]))
    assert any("duplicate model name: m1" in i for i in issues)


def test_dataset_larger_than_max_cases_is_rejected(tmp_path: Path) -> None:
    issues = _issues(tmp_path, _config(run={"max_cases": 1}))
    assert any("exceeds run.max_cases=1" in i for i in issues)


def test_missing_dataset_and_invalid_yaml(tmp_path: Path) -> None:
    with pytest.raises(InputValidationError, match="file not found"):
        load_config(_setup(tmp_path, _config(dataset="nope.json")))
    bad = tmp_path / "bad.yaml"
    bad.write_text("models: [unclosed", encoding="utf-8")
    with pytest.raises(InputValidationError, match="invalid YAML"):
        load_config(bad)


def test_gate_file_is_loaded_and_validated(tmp_path: Path) -> None:
    rule = {"metric": "exact_match", "aggregation": "mean", "operator": "gte", "threshold": 1}
    (tmp_path / "gates.yaml").write_text(yaml.safe_dump({"rules": [rule]}), encoding="utf-8")
    loaded = load_config(_setup(tmp_path, _config(gates="gates.yaml")))
    assert loaded.gate is not None and len(loaded.gate.rules) == 1

    (tmp_path / "gates.yaml").write_text(yaml.safe_dump({"rules": []}), encoding="utf-8")
    with pytest.raises(InputValidationError):
        load_config(_setup(tmp_path, _config(gates="gates.yaml")))
