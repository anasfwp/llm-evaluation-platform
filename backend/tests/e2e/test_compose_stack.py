"""End-to-end workflow against a running stack: API, PostgreSQL, Redis, and the Celery worker.

Skipped unless ``E2E_API_URL`` points at the stack, which CI starts with Docker Compose:

    docker compose up -d --build --wait
    E2E_API_URL=http://127.0.0.1:8000 uv run pytest backend/tests/e2e/test_compose_stack.py
"""

from __future__ import annotations

import copy
import json
import os
import time
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml

from app.cli.main import EXIT_GATE_FAILED, main

API_URL = os.environ.get("E2E_API_URL")
pytestmark = pytest.mark.skipif(not API_URL, reason="E2E_API_URL is not set")

REPO_ROOT = Path(__file__).resolve().parents[3]
METRICS = [{"name": "exact_match"}, {"name": "latency"}]
# Makes the noisy model newly fail a case that it answers correctly in the first run.
DRIFT = {"science-water-formula": {"output": "Water"}}


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    with httpx.Client(base_url=f"{API_URL}/api/v1", timeout=30) as http:
        yield http


def _ok(response: httpx.Response) -> Any:
    assert response.is_success, f"{response.request.url} -> {response.status_code}: {response.text}"
    return response.json() if response.content else None


def _finish(client: httpx.Client, body: dict[str, Any]) -> dict[str, Any]:
    started = client.post("/runs", json=body)
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]
    for _ in range(120):
        run: dict[str, Any] = _ok(client.get(f"/runs/{run_id}"))
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.5)
    pytest.fail(f"run {run_id} did not finish; is the worker running?")


def test_full_workflow_through_the_worker(client: httpx.Client, tmp_path: Path) -> None:
    project = _ok(client.post("/projects", json={"name": f"e2e-{uuid.uuid4().hex[:8]}"}))
    dataset_path = REPO_ROOT / "datasets" / "demo_qa.json"
    with dataset_path.open("rb") as handle:
        dataset = _ok(
            client.post(
                "/datasets/import",
                data={"project_id": project["id"]},
                files={"file": (dataset_path.name, handle, "application/json")},
            )
        )

    config = yaml.safe_load((REPO_ROOT / "evals" / "demo_config.yaml").read_text(encoding="utf-8"))
    models = {
        spec["name"]: _ok(
            client.post(
                f"/projects/{project['id']}/models",
                json={k: spec[k] for k in ("name", "provider", "model_id", "parameters")},
            )
        )
        for spec in config["models"]
    }
    body = {
        "project_id": project["id"],
        "dataset_id": dataset["id"],
        "model_config_ids": [model["id"] for model in models.values()],
        "metrics": METRICS,
        "run_config": {"max_retries": 0},
    }

    baseline = _finish(client, body)
    assert baseline["status"] == "completed"
    assert baseline["progress"]["completed_cases"] == 2 * dataset["case_count"]

    # A failed case is recorded and does not affect the other results.
    failed = _ok(client.get(f"/runs/{baseline['id']}/results", params={"status": "error"}))
    assert [row["error_code"] for row in failed["items"]] == ["rate_limited"]

    noisy = next(spec for spec in config["models"] if spec["name"] == "fake-noisy")
    parameters = copy.deepcopy(noisy["parameters"])
    parameters["overrides"].update(DRIFT)
    _ok(client.patch(f"/models/{models['fake-noisy']['id']}", json={"parameters": parameters}))
    candidate = _finish(client, body)
    assert candidate["status"] == "completed"

    comparison = _ok(
        client.post(
            "/comparisons",
            json={"baseline_run_id": baseline["id"], "candidate_run_id": candidate["id"]},
        )
    )
    assert comparison["result"]["regressed"] is True

    # A dataset that runs depend on cannot be deleted.
    assert client.delete(f"/datasets/{dataset['id']}").status_code == 409

    # The API's report works with the CLI, and a deliberately strict gate fails the build.
    report = _ok(client.get(f"/runs/{candidate['id']}/report", params={"format": "json"}))
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    rules_path = tmp_path / "gates.yaml"
    rules_path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1.0",
                "name": "strict",
                "missing_metric_policy": "fail",
                "rules": [
                    {
                        "metric": "exact_match",
                        "aggregation": "mean",
                        "operator": "gte",
                        "threshold": 0.99,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    code = main(["gate", "--report", str(report_path), "--rules", str(rules_path)])
    assert code == EXIT_GATE_FAILED
