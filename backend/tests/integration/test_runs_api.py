from __future__ import annotations

import csv
import io
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.db.models import EvaluationRun
from app.services.run_service import execute_run
from tests.integration.conftest import JsonDict, ModelFactory, RecordingDispatcher

FAST_RUN = {"max_retries": 0, "retry_backoff_seconds": 0, "max_concurrency": 2}
METRICS = [{"name": "exact_match", "version": "1.0"}, {"name": "latency"}]


def _start(client: TestClient, dataset: JsonDict, models: list[JsonDict], **extra: Any) -> Any:
    payload = {
        "project_id": dataset["project_id"],
        "dataset_id": dataset["id"],
        "model_config_ids": [m["id"] for m in models],
        "metrics": METRICS,
        "run_config": FAST_RUN,
    }
    payload.update(extra)
    return client.post("/api/v1/runs", json=payload)


@pytest.fixture
def two_models(make_model: ModelFactory) -> list[JsonDict]:
    return [
        make_model("reference"),
        make_model(
            "noisy",
            overrides={"case-1": {"output": "wrong"}, "case-2": {"error": "rate_limited"}},
        ),
    ]


@pytest.fixture
def finished_run(client: TestClient, dataset: JsonDict, two_models: list[JsonDict]) -> JsonDict:
    accepted = _start(client, dataset, two_models)
    assert accepted.status_code == 202, accepted.text
    run_id = accepted.json()["run_id"]
    assert accepted.json()["status_url"] == f"/api/v1/runs/{run_id}"
    run: JsonDict = client.get(f"/api/v1/runs/{run_id}").json()
    return run


def test_metric_catalog(client: TestClient) -> None:
    names = {m["name"] for m in client.get("/api/v1/metrics").json()}
    assert {"exact_match", "latency"} <= names


def test_run_completes_with_partial_failure(finished_run: JsonDict) -> None:
    assert finished_run["status"] == "completed"
    assert finished_run["progress"] == {"total_cases": 10, "completed_cases": 10, "failed_cases": 1}
    assert finished_run["dataset"]["name"] == "qa"
    assert finished_run["dataset"]["version"] == 1
    assert finished_run["config_hash"].startswith("sha256:")
    assert finished_run["started_at"] is not None
    assert finished_run["finished_at"] is not None

    summaries = {s["model_name"]: s for s in finished_run["models"]}
    assert summaries["reference"]["error_count"] == 0
    assert summaries["reference"]["metrics"]["exact_match"]["mean"] == 1.0
    noisy = summaries["noisy"]
    assert noisy["error_count"] == 1
    assert noisy["error_rate"] == pytest.approx(0.2)
    assert noisy["error_codes"] == {"rate_limited": 1}
    # 3 scorable successes (case-0, case-1, case-3): errored and unanswerable cases are excluded.
    assert noisy["metrics"]["exact_match"]["scored_count"] == 3
    assert noisy["metrics"]["exact_match"]["mean"] == pytest.approx(2 / 3)


def test_run_snapshot_is_stable_after_model_edit(
    client: TestClient, finished_run: JsonDict, two_models: list[JsonDict]
) -> None:
    client.patch(f"/api/v1/models/{two_models[0]['id']}", json={"model_id": "edited"})
    run = client.get(f"/api/v1/runs/{finished_run['id']}").json()
    model_ids = [m["model_id"] for m in run["config_snapshot"]["models"]]
    assert model_ids == ["reference-v1", "noisy-v1"]
    assert run["config_hash"] == finished_run["config_hash"]


def test_result_filters(client: TestClient, finished_run: JsonDict) -> None:
    url = f"/api/v1/runs/{finished_run['id']}/results"
    everything = client.get(url).json()
    assert everything["total"] == 10

    errors = client.get(url, params={"status": "error"}).json()
    assert [(r["model_name"], r["case_key"]) for r in errors["items"]] == [("noisy", "case-2")]
    assert errors["items"][0]["error_code"] == "rate_limited"
    assert errors["items"][0]["actual_output"] is None

    noisy_misses = client.get(
        url, params={"model_name": "noisy", "metric": "exact_match", "max_score": 0}
    ).json()
    assert [r["case_key"] for r in noisy_misses["items"]] == ["case-1"]

    odd = client.get(url, params={"tag": "odd", "model_name": "reference"}).json()
    assert {r["case_key"] for r in odd["items"]} == {"case-1", "case-3"}

    first = everything["items"][0]
    single = client.get(f"{url}/{first['id']}").json()
    assert single == first
    assert {m["metric_name"] for m in single["metrics"]} == {"exact_match", "latency"}
    assert client.get(f"{url}/{uuid.uuid4()}").status_code == 404


def test_reports(client: TestClient, finished_run: JsonDict) -> None:
    url = f"/api/v1/runs/{finished_run['id']}/report"

    report = client.get(url).json()
    assert report["run_id"] == finished_run["id"]
    assert report["status"] == "completed"
    assert report["config_hash"] == finished_run["config_hash"]
    assert len(report["results"]) == 10
    assert [s["model_name"] for s in report["summaries"]] == ["reference", "noisy"]
    # Results follow the configured model order, then dataset order.
    assert [r["case_key"] for r in report["results"][:2]] == ["case-0", "case-1"]

    as_csv = client.get(url, params={"format": "csv"})
    assert as_csv.status_code == 200
    assert as_csv.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(as_csv.text)))
    assert len(rows) == 10

    markdown = client.get(url, params={"format": "markdown"})
    assert markdown.status_code == 200
    assert "noisy" in markdown.text
    assert client.get(url, params={"format": "pdf"}).status_code == 422


def test_list_runs(client: TestClient, finished_run: JsonDict) -> None:
    listed = client.get("/api/v1/runs", params={"project_id": finished_run["project_id"]}).json()
    assert [r["id"] for r in listed["items"]] == [finished_run["id"]]
    queued = client.get("/api/v1/runs", params={"status": "queued"}).json()
    assert queued["total"] == 0


def test_queued_run_can_be_cancelled(
    client: TestClient,
    dataset: JsonDict,
    two_models: list[JsonDict],
    recording_dispatcher: RecordingDispatcher,
) -> None:
    run_id = _start(client, dataset, two_models).json()["run_id"]
    assert recording_dispatcher.dispatched == [uuid.UUID(run_id)]
    assert client.get(f"/api/v1/runs/{run_id}").json()["status"] == "queued"

    report = client.get(f"/api/v1/runs/{run_id}/report")
    assert report.status_code == 409
    assert report.json()["error"]["code"] == "CONFLICT"

    cancelled = client.post(f"/api/v1/runs/{run_id}/cancel")
    assert cancelled.status_code == 202
    assert cancelled.json()["status"] == "cancelled"
    assert client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 409

    # A late worker delivery must not resurrect a cancelled run.
    execute_run(client.app.state.session_factory, uuid.UUID(run_id))  # type: ignore[attr-defined]
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "cancelled"
    assert run["progress"]["completed_cases"] == 0
    assert client.get(f"/api/v1/runs/{run_id}/report").status_code == 200


def test_cancel_requested_before_execution_stops_cases(
    client: TestClient,
    dataset: JsonDict,
    two_models: list[JsonDict],
    recording_dispatcher: RecordingDispatcher,
) -> None:
    run_id = uuid.UUID(_start(client, dataset, two_models).json()["run_id"])
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    with session_factory() as session:
        row = session.get(EvaluationRun, run_id)
        assert row is not None
        row.cancel_requested = True  # as if requested while the worker was starting
        session.commit()

    execute_run(session_factory, run_id)
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "cancelled"
    assert run["progress"]["completed_cases"] == 0


def test_completed_run_is_not_executed_twice(client: TestClient, finished_run: JsonDict) -> None:
    session_factory = client.app.state.session_factory  # type: ignore[attr-defined]
    execute_run(session_factory, uuid.UUID(finished_run["id"]))
    results = client.get(f"/api/v1/runs/{finished_run['id']}/results").json()
    assert results["total"] == 10


class _BrokenDispatcher:
    def dispatch(self, run_id: uuid.UUID) -> None:
        raise ConnectionError("redis down")


def test_dispatch_failure_marks_run_failed(
    client: TestClient, dataset: JsonDict, two_models: list[JsonDict]
) -> None:
    client.app.state.dispatcher = _BrokenDispatcher()  # type: ignore[attr-defined]
    response = _start(client, dataset, two_models)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    runs = client.get("/api/v1/runs").json()["items"]
    assert [r["status"] for r in runs] == ["failed"]


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"metrics": [{"name": "no_such_metric"}]}, "metrics[0]"),
        ({"metrics": [{"name": "exact_match", "version": "9.9"}]}, "metrics[0]"),
        ({"dataset_version": 7}, "dataset_version"),
    ],
)
def test_invalid_run_requests(
    client: TestClient,
    dataset: JsonDict,
    two_models: list[JsonDict],
    override: JsonDict,
    field: str,
) -> None:
    response = _start(client, dataset, two_models, **override)
    assert response.status_code == 422
    assert field in {d["field"] for d in response.json()["error"]["details"]}
    assert client.get("/api/v1/runs").json()["total"] == 0


def test_duplicate_and_foreign_models_rejected(
    client: TestClient, dataset: JsonDict, two_models: list[JsonDict]
) -> None:
    duplicate = _start(client, dataset, [two_models[0], two_models[0]])
    assert duplicate.status_code == 422

    other = client.post("/api/v1/projects", json={"name": "other"}).json()
    foreign = client.post(
        f"/api/v1/projects/{other['id']}/models",
        json={"name": "foreign", "provider": "fake", "model_id": "m"},
    ).json()
    response = _start(client, dataset, [two_models[0], foreign])
    assert response.status_code == 422
    assert "model_config_ids[1]" in {d["field"] for d in response.json()["error"]["details"]}


def test_runs_rejected_for_archived_project(
    client: TestClient, dataset: JsonDict, two_models: list[JsonDict]
) -> None:
    client.delete(f"/api/v1/projects/{dataset['project_id']}")
    response = _start(client, dataset, two_models)
    assert response.status_code == 409
    assert "archived" in response.json()["error"]["message"]


def test_run_estimates_cost_with_frozen_pricing(
    client: TestClient, dataset: JsonDict, make_model: ModelFactory
) -> None:
    accepted = _start(
        client, dataset, [make_model("priced")], metrics=[*METRICS, {"name": "estimated_cost"}]
    )
    assert accepted.status_code == 202, accepted.text
    run = client.get(f"/api/v1/runs/{accepted.json()['run_id']}").json()
    assert run["status"] == "completed"
    # The pricing table used is part of the snapshot (and therefore the config hash).
    cost_config = run["config_snapshot"]["metrics"][2]["config"]
    assert cost_config["pricing"]["pricing_version"]

    summary = client.get(f"/api/v1/runs/{run['id']}/report").json()["summaries"][0]
    cost = summary["metrics"]["estimated_cost"]
    assert cost["scored_count"] == summary["success_count"]
    assert cost["total"] == pytest.approx(cost["mean"] * cost["scored_count"])
    assert cost["total"] > 0


def test_run_rechecks_env_allowlist(
    client: TestClient, dataset: JsonDict, project: JsonDict
) -> None:
    model = client.post(
        f"/api/v1/projects/{project['id']}/models",
        json={"name": "claude", "provider": "anthropic", "model_id": "claude-opus-5-5"},
    ).json()
    client.app.state.settings.provider_env_allowlist = "OPENAI_API_KEY"  # type: ignore[attr-defined]
    response = _start(client, dataset, [model])
    assert response.status_code == 422
    assert "ANTHROPIC_API_KEY" in response.text


def test_judge_metric_runs_and_disallowed_judge_env_is_rejected(
    client: TestClient, dataset: JsonDict, make_model: ModelFactory
) -> None:
    model = make_model("reference")
    fake_judge = {
        "name": "llm_judge_correctness",
        "config": {
            "judge": {"provider": "fake", "model_id": "fake-judge", "parameters": {"mode": "judge"}}
        },
    }
    accepted = _start(client, dataset, [model], metrics=[fake_judge])
    assert accepted.status_code == 202, accepted.text
    run = client.get(f"/api/v1/runs/{accepted.json()['run_id']}").json()
    stats = run["models"][0]["metrics"]["llm_judge_correctness"]
    assert stats["mean"] == 5.0
    assert stats["not_applicable_count"] == 1  # the open-ended case has no reference

    sneaky = {
        "name": "llm_judge_correctness",
        "config": {
            "judge": {
                "provider": "anthropic",
                "model_id": "claude-haiku-5-5",
                "secret_reference": "DATABASE_URL",
            }
        },
    }
    rejected = _start(client, dataset, [model], metrics=[sneaky])
    assert rejected.status_code == 422
    fields = [d["field"] for d in rejected.json()["error"]["details"]]
    assert fields == ["metrics[0].config.judge.secret_reference"]
