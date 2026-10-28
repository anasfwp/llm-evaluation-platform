from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import JsonDict, ModelFactory, RecordingDispatcher

FAST_RUN = {"max_retries": 0, "retry_backoff_seconds": 0}
METRICS = [{"name": "exact_match"}, {"name": "latency"}]
EM_ABSOLUTE = {"metric": "exact_match", "aggregation": "mean", "operator": "gte", "threshold": 0.9}
EM_RELATIVE = {
    "metric": "exact_match",
    "aggregation": "mean",
    "kind": "relative",
    "max_regression": 0.1,
}


def _run(client: TestClient, dataset: JsonDict, model: JsonDict) -> str:
    response = client.post(
        "/api/v1/runs",
        json={
            "project_id": dataset["project_id"],
            "dataset_id": dataset["id"],
            "model_config_ids": [model["id"]],
            "metrics": METRICS,
            "run_config": FAST_RUN,
        },
    )
    assert response.status_code == 202, response.text
    run_id: str = response.json()["run_id"]
    return run_id


@pytest.fixture
def runs(client: TestClient, dataset: JsonDict, make_model: ModelFactory) -> dict[str, str]:
    """A good baseline run and a worse candidate run, from same-named models in two runs."""
    good = make_model("good")
    baseline = _run(client, dataset, good)
    client.patch(
        f"/api/v1/models/{good['id']}",
        json={"parameters": {"overrides": {"case-1": {"output": "wrong"}}}},
    )
    candidate = _run(client, dataset, good)
    return {"baseline": baseline, "candidate": candidate}


def test_create_and_read_comparison(client: TestClient, runs: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/comparisons",
        json={"baseline_run_id": runs["baseline"], "candidate_run_id": runs["candidate"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    result = body["result"]
    assert result["regressed"] is True
    assert result["newly_failing_count"] == 1
    assert result["models"][0]["newly_failing"][0]["case_key"] == "case-1"

    fetched = client.get(f"/api/v1/comparisons/{body['id']}").json()
    assert fetched == body
    listed = client.get("/api/v1/comparisons", params={"project_id": body["project_id"]}).json()
    assert listed["total"] == 1
    assert listed["items"][0]["regressed"] is True
    markdown = client.get(f"/api/v1/comparisons/{body['id']}/report")
    assert markdown.status_code == 200
    assert "Newly failing" in markdown.text
    as_json = client.get(f"/api/v1/comparisons/{body['id']}/report", params={"format": "json"})
    assert as_json.json()["models"][0]["cases_compared"] == 5


def test_comparison_validation(
    client: TestClient,
    runs: dict[str, str],
    dataset: JsonDict,
    make_model: ModelFactory,
    recording_dispatcher: RecordingDispatcher,
) -> None:
    both = client.post(
        "/api/v1/comparisons",
        json={
            "baseline_run_id": runs["baseline"],
            "baseline_id": runs["baseline"],
            "candidate_run_id": runs["candidate"],
        },
    )
    assert both.status_code == 422

    queued = _run(client, dataset, make_model("other"))  # stays queued: recording dispatcher
    not_done = client.post(
        "/api/v1/comparisons",
        json={"baseline_run_id": runs["baseline"], "candidate_run_id": queued},
    )
    assert not_done.status_code == 409
    assert "only completed runs" in not_done.json()["error"]["message"]

    bad_pair = client.post(
        "/api/v1/comparisons",
        json={
            "baseline_run_id": runs["baseline"],
            "candidate_run_id": runs["candidate"],
            "settings": {"model_pairs": [{"baseline": "ghost", "candidate": "good"}]},
        },
    )
    assert bad_pair.status_code == 422


def test_baselines_crud_and_use(
    client: TestClient, project: JsonDict, runs: dict[str, str]
) -> None:
    url = f"/api/v1/projects/{project['id']}/baselines"
    created = client.post(url, json={"name": "release-1", "run_id": runs["baseline"]})
    assert created.status_code == 201, created.text
    baseline = created.json()
    assert client.post(url, json={"name": "release-1", "run_id": runs["baseline"]}).status_code == (
        409
    )
    assert [b["name"] for b in client.get(url).json()] == ["release-1"]

    comparison = client.post(
        "/api/v1/comparisons",
        json={"baseline_id": baseline["id"], "candidate_run_id": runs["candidate"]},
    )
    assert comparison.status_code == 201
    assert comparison.json()["baseline_run_id"] == runs["baseline"]

    moved = client.patch(f"/api/v1/baselines/{baseline['id']}", json={"run_id": runs["candidate"]})
    assert moved.json()["run_id"] == runs["candidate"]
    assert client.delete(f"/api/v1/baselines/{baseline['id']}").status_code == 204
    assert client.get(f"/api/v1/baselines/{baseline['id']}").status_code == 404
    # The run itself is untouched.
    assert client.get(f"/api/v1/runs/{runs['candidate']}").status_code == 200


def test_saved_gate_and_relative_evaluation(
    client: TestClient, project: JsonDict, runs: dict[str, str]
) -> None:
    url = f"/api/v1/projects/{project['id']}/gates"
    created = client.post(url, json={"name": "release", "rules": [EM_ABSOLUTE, EM_RELATIVE]})
    assert created.status_code == 201, created.text
    gate = created.json()
    assert gate["rules"][1]["kind"] == "relative"
    assert [g["name"] for g in client.get(url).json()] == ["release"]

    # Without a baseline the relative rule falls under the (default fail) missing policy.
    alone = client.post(
        "/api/v1/gates/evaluate", json={"run_id": runs["baseline"], "gate_id": gate["id"]}
    ).json()
    assert alone["passed"] is False
    assert "no baseline" in alone["results"][1]["reason"]

    against = client.post(
        "/api/v1/gates/evaluate",
        json={
            "run_id": runs["candidate"],
            "gate_id": gate["id"],
            "baseline_run_id": runs["baseline"],
        },
    ).json()
    assert against["passed"] is False
    assert against["baseline_run_id"] == runs["baseline"]
    relative = against["results"][1]
    assert relative["status"] == "failed"
    assert relative["regression"] == pytest.approx(0.25)

    updated = client.patch(
        f"/api/v1/gates/{gate['id']}",
        json={"rules": [{**EM_RELATIVE, "max_regression": 0.5}]},
    )
    assert updated.status_code == 200
    relaxed = client.post(
        "/api/v1/gates/evaluate",
        json={
            "run_id": runs["candidate"],
            "gate_id": gate["id"],
            "baseline_run_id": runs["baseline"],
        },
    ).json()
    assert relaxed["passed"] is True


def test_inline_gate_evaluation(client: TestClient, runs: dict[str, str]) -> None:
    payload: dict[str, Any] = {
        "run_id": runs["baseline"],
        "rules": [EM_ABSOLUTE, {"metric": "error_rate", "aggregation": "overall",
                               "operator": "lte", "threshold": 0}],
    }  # fmt: skip
    result = client.post("/api/v1/gates/evaluate", json=payload)
    assert result.status_code == 200, result.text
    assert result.json()["passed"] is True
    neither = client.post("/api/v1/gates/evaluate", json={"run_id": runs["baseline"]})
    assert neither.status_code == 422
    bad_rule = client.post(
        "/api/v1/gates/evaluate",
        json={"run_id": runs["baseline"], "rules": [{"metric": "x", "aggregation": "mean"}]},
    )
    assert bad_rule.status_code == 422
