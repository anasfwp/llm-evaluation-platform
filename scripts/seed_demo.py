"""Load the demo into a running API so the dashboard has something to show.

Creates a project, imports ``datasets/demo_qa.json``, registers the two fake
models from ``evals/demo_config.yaml``, runs a short history of evaluations
(the noisy model gets worse in the last one), saves a baseline and a gate, and
compares the latest run with the baseline. Uses only the fake provider: no
credentials or network calls beyond the local API.

    python scripts/seed_demo.py [--api http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import copy
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "demo-project"
METRICS = [
    {"name": "exact_match"},
    {"name": "token_f1"},
    {"name": "latency"},
    {"name": "estimated_cost"},
]
RUN_CONFIG = {"max_retries": 1, "retry_backoff_seconds": 0.1}
GATE_RULES = [
    {"metric": "exact_match", "aggregation": "mean", "operator": "gte", "threshold": 0.8},
    {"metric": "error_rate", "aggregation": "overall", "operator": "lte", "threshold": 0.1},
    {"metric": "exact_match", "aggregation": "mean", "kind": "relative", "max_regression": 0.02},
]
# Extra wrong answers for the noisy model in the later runs, to give the trend some shape.
DRIFT = [
    {},
    {"science-water-formula": {"output": "Water"}},
    {"science-water-formula": {"output": "Water"}, "geo-largest-ocean": {"output": "Atlantic"}},
]


def check(response: httpx.Response) -> Any:
    if response.is_error:
        request = response.request
        sys.exit(f"{request.method} {request.url} -> {response.status_code}: {response.text}")
    return response.json() if response.content else None


def wait_for(client: httpx.Client, run_id: str) -> dict[str, Any]:
    for _ in range(300):
        run: dict[str, Any] = check(client.get(f"/runs/{run_id}"))
        if run["status"] in {"completed", "failed", "cancelled"}:
            return run
        time.sleep(0.5)
    sys.exit(f"run {run_id} did not finish; is the worker running?")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL")
    args = parser.parse_args()

    config = yaml.safe_load((ROOT / "evals" / "demo_config.yaml").read_text(encoding="utf-8"))
    with httpx.Client(base_url=f"{args.api.rstrip('/')}/api/v1", timeout=30) as client:
        existing = check(client.get("/projects", params={"limit": 200}))["items"]
        if any(p["name"] == PROJECT for p in existing):
            sys.exit(f"project '{PROJECT}' already exists; archive it or use a fresh database")
        project = check(
            client.post(
                "/projects",
                json={"name": PROJECT, "description": "Demo data from scripts/seed_demo.py"},
            )
        )
        pid = project["id"]

        dataset_path = ROOT / "datasets" / "demo_qa.json"
        with dataset_path.open("rb") as handle:
            dataset = check(
                client.post(
                    "/datasets/import",
                    data={"project_id": pid},
                    files={"file": (dataset_path.name, handle, "application/json")},
                )
            )

        models = {}
        for spec in config["models"]:
            body = {k: spec[k] for k in ("name", "provider", "model_id", "parameters")}
            models[spec["name"]] = check(client.post(f"/projects/{pid}/models", json=body))
        noisy = next(s for s in config["models"] if s["name"] == "fake-noisy")

        run_ids = []
        for drift in DRIFT:
            parameters = copy.deepcopy(noisy["parameters"])
            parameters["overrides"].update(drift)
            check(
                client.patch(
                    f"/models/{models['fake-noisy']['id']}", json={"parameters": parameters}
                )
            )
            started = check(
                client.post(
                    "/runs",
                    json={
                        "project_id": pid,
                        "dataset_id": dataset["id"],
                        "model_config_ids": [m["id"] for m in models.values()],
                        "metrics": METRICS,
                        "run_config": RUN_CONFIG,
                    },
                )
            )
            run = wait_for(client, started["run_id"])
            print(f"run {run['id']}: {run['status']}")
            run_ids.append(run["id"])
            if len(run_ids) == 1:
                check(
                    client.post(
                        f"/projects/{pid}/baselines",
                        json={
                            "name": "release-1",
                            "run_id": run["id"],
                            "description": "First demo run",
                        },
                    )
                )

        baseline = check(client.get(f"/projects/{pid}/baselines"))[0]
        gate = check(
            client.post(f"/projects/{pid}/gates", json={"name": "release", "rules": GATE_RULES})
        )
        result = check(
            client.post(
                "/gates/evaluate",
                json={"run_id": run_ids[-1], "gate_id": gate["id"], "baseline_id": baseline["id"]},
            )
        )
        comparison = check(
            client.post(
                "/comparisons",
                json={"baseline_id": baseline["id"], "candidate_run_id": run_ids[-1]},
            )
        )

    print(f"gate '{gate['name']}' on the latest run: {'PASSED' if result['passed'] else 'FAILED'}")
    print(f"comparison {comparison['id']}: regressed={comparison['result']['regressed']}")
    print(f"project: /projects/{pid}")


if __name__ == "__main__":
    main()
