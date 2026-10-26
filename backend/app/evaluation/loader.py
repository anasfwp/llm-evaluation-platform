"""Load and fully validate evaluation configs, datasets, gate rules, and reports
without making any model calls. Shared by the CLI and, later, the API."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.core.errors import InputValidationError, Issue, issues_from_validation_error
from app.domain.datasets import Dataset, load_dataset
from app.domain.gates import GateConfig
from app.domain.runs import EvalConfig, RunReport
from app.evaluation.engine import RunPlan
from app.evaluation.metrics.base import Metric
from app.evaluation.registry import build_metric
from app.providers.registry import get_provider


@dataclass(frozen=True)
class LoadedConfig:
    path: Path
    config: EvalConfig
    dataset_path: Path
    dataset: Dataset
    metrics: list[Metric]
    gate_path: Path | None
    gate: GateConfig | None

    def resolve(self, relative: str) -> Path:
        return _resolve(self.path, relative)

    def build_plan(self) -> RunPlan:
        adapters = {
            model.name: get_provider(model.provider).from_config(model, dataset=self.dataset)
            for model in self.config.models
        }
        return RunPlan(
            config=self.config,
            dataset=self.dataset,
            dataset_source=self.config.dataset,
            metrics=self.metrics,
            adapters=adapters,
        )


def _resolve(config_path: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute():
        return candidate
    return Path(os.path.normpath(config_path.parent / candidate))


def _read_yaml(path: Path) -> Any:
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputValidationError(source, [Issue("", "file not found")]) from None
    except OSError as exc:
        raise InputValidationError(source, [Issue("", f"cannot read file: {exc}")]) from None
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise InputValidationError(source, [Issue("", f"invalid YAML: {exc}")]) from None


def load_gate_config(path: Path) -> GateConfig:
    raw = _read_yaml(path)
    try:
        return GateConfig.model_validate(raw)
    except ValidationError as exc:
        raise InputValidationError(str(path), issues_from_validation_error(exc)) from None


def load_report(path: Path) -> RunReport:
    source = str(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise InputValidationError(source, [Issue("", "file not found")]) from None
    try:
        return RunReport.model_validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise InputValidationError(source, [Issue("", f"invalid JSON: {exc.msg}")]) from None
    except ValidationError as exc:
        raise InputValidationError(source, issues_from_validation_error(exc)) from None


def load_config(path: Path, *, gate_override: Path | None = None) -> LoadedConfig:
    """Validate the config, its dataset, provider parameters, metrics, and gate rules."""
    source = str(path)
    raw = _read_yaml(path)
    try:
        config = EvalConfig.model_validate(raw)
    except ValidationError as exc:
        raise InputValidationError(source, issues_from_validation_error(exc)) from None

    issues: list[Issue] = []
    for index, model in enumerate(config.models):
        location = f"models[{index}]"
        try:
            provider = get_provider(model.provider)
        except KeyError as exc:
            issues.append(Issue(f"{location}.provider", str(exc.args[0])))
            continue
        try:
            provider.Parameters.model_validate(model.parameters)
        except ValidationError as exc:
            issues.extend(issues_from_validation_error(exc, prefix=f"{location}.parameters"))

    metrics: list[Metric] = []
    for index, selection in enumerate(config.metrics):
        try:
            metrics.append(build_metric(selection.name, selection.version, selection.config))
        except ValidationError as exc:
            issues.extend(issues_from_validation_error(exc, prefix=f"metrics[{index}].config"))
        except ValueError as exc:
            issues.append(Issue(f"metrics[{index}]", str(exc)))

    if issues:
        raise InputValidationError(source, issues)

    dataset_path = _resolve(path, config.dataset)
    dataset = load_dataset(dataset_path)
    if len(dataset.cases) > config.run.max_cases:
        raise InputValidationError(
            str(dataset_path),
            [
                Issue(
                    "cases",
                    f"{len(dataset.cases)} cases exceeds run.max_cases={config.run.max_cases}",
                )
            ],
        )

    gate_path = gate_override or (_resolve(path, config.gates) if config.gates else None)
    gate = load_gate_config(gate_path) if gate_path is not None else None

    return LoadedConfig(
        path=path,
        config=config,
        dataset_path=dataset_path,
        dataset=dataset,
        metrics=metrics,
        gate_path=gate_path,
        gate=gate,
    )
