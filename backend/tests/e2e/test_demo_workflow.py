"""End-to-end CLI workflow on the shipped demo config, using only the fake provider."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from app.cli.main import (
    EXIT_GATE_FAILED,
    EXIT_INVALID_INPUT,
    EXIT_OK,
    EXIT_RUN_FAILED,
    main,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_CONFIG = REPO_ROOT / "evals" / "demo_config.yaml"
DEMO_GATES = REPO_ROOT / "evals" / "gates.example.yaml"


def _write_yaml(path: Path, data: object) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_validate_demo_config() -> None:
    assert main(["validate", "--config", str(DEMO_CONFIG)]) == EXIT_OK


def test_demo_run_writes_reports_and_passes_gate(tmp_path: Path) -> None:
    report_path = tmp_path / "run.json"
    markdown_path = tmp_path / "run.md"
    code = main(
        [
            "run",
            "--config", str(DEMO_CONFIG),
            "--output", str(report_path),
            "--markdown", str(markdown_path),
        ]
    )  # fmt: skip
    assert code == EXIT_OK

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "completed"
    assert report["dataset"]["case_count"] == 21
    assert report["dataset"]["content_hash"].startswith("sha256:")
    assert report["gate"]["passed"] is True
    assert len(report["results"]) == 42  # 21 cases x 2 models

    summaries = {s["model_name"]: s for s in report["summaries"]}
    assert summaries["fake-reference"]["metrics"]["exact_match"]["mean"] == 1.0
    noisy = summaries["fake-noisy"]
    assert noisy["metrics"]["exact_match"]["mean"] == pytest.approx(16 / 19)
    assert noisy["error_codes"] == {"rate_limited": 1}

    errored = next(r for r in report["results"] if r["case_key"] == "cs-http-not-found"
                   and r["model_name"] == "fake-noisy")  # fmt: skip
    assert errored["status"] == "error"
    assert errored["attempts"] == 2  # transient error retried once
    open_ended = next(r for r in report["results"] if r["case_key"] == "open-greeting")
    assert open_ended["metrics"][0]["status"] == "not_applicable"

    markdown = markdown_path.read_text(encoding="utf-8")
    assert "## Gate `demo-release-gate`: PASSED" in markdown
    assert "capital-australia" in markdown


def test_strict_gate_fails_with_exit_code_1(tmp_path: Path) -> None:
    strict = _write_yaml(
        tmp_path / "strict.yaml",
        {"rules": [{"metric": "exact_match", "aggregation": "mean", "operator": "gte",
                    "threshold": 0.95}]},
    )  # fmt: skip
    report_path = tmp_path / "run.json"
    code = main(
        ["run", "--config", str(DEMO_CONFIG), "--gates", str(strict), "--output", str(report_path)]
    )
    assert code == EXIT_GATE_FAILED

    # The standalone gate command reaches the same verdicts from the saved report.
    assert main(["gate", "--report", str(report_path), "--rules", str(strict)]) == EXIT_GATE_FAILED
    assert main(["gate", "--report", str(report_path), "--rules", str(DEMO_GATES)]) == EXIT_OK


def test_invalid_config_exits_2_and_names_the_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = yaml.safe_load(DEMO_CONFIG.read_text(encoding="utf-8"))
    config["dataset"] = str(REPO_ROOT / "datasets" / "demo_qa.json")
    config["models"][0]["provider"] = "nonexistent"
    config.pop("gates")
    path = _write_yaml(tmp_path / "bad.yaml", config)

    assert main(["run", "--config", str(path)]) == EXIT_INVALID_INPUT
    assert "models[0].provider" in capsys.readouterr().err


def test_model_with_every_case_failing_exits_3(tmp_path: Path) -> None:
    dataset = {
        "schema_version": "1.0",
        "name": "tiny",
        "cases": [{"case_key": "c1", "input": {"q": "x"}, "expected_output": "y"}],
    }
    (tmp_path / "tiny.json").write_text(json.dumps(dataset), encoding="utf-8")
    config = {
        "project": "p",
        "dataset": "tiny.json",
        "models": [
            {
                "name": "down",
                "provider": "fake",
                "model_id": "f",
                "parameters": {"overrides": {"c1": {"error": "authentication_failed"}}},
            }
        ],
        "metrics": [{"name": "exact_match"}],
    }
    path = _write_yaml(tmp_path / "eval.yaml", config)
    assert main(["run", "--config", str(path), "--json"]) == EXIT_RUN_FAILED


def test_metrics_list_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["metrics", "list", "--json"]) == EXIT_OK
    names = [m["name"] for m in json.loads(capsys.readouterr().out)]
    assert names == ["exact_match", "latency", "estimated_cost"]
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
