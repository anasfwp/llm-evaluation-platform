"""Full API flow on the RAG demo dataset: import, run with a judge metric, inspect, export."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi.testclient import TestClient

from tests.integration.conftest import JsonDict, ModelFactory

DATASET = Path(__file__).resolve().parents[3] / "datasets" / "demo_rag.json"
JUDGE = {
    "judge": {"provider": "fake", "model_id": "fake-judge-v1", "parameters": {"mode": "judge"}}
}


def test_rag_run_through_the_api(
    client: TestClient, project: JsonDict, make_model: ModelFactory
) -> None:
    with DATASET.open("rb") as handle:
        imported = client.post(
            "/api/v1/datasets/import",
            data={"project_id": project["id"]},
            files={"file": ("demo_rag.json", handle, "application/json")},
        )
    assert imported.status_code == 201, imported.text
    dataset = imported.json()
    assert dataset["case_count"] == 7

    version = client.get(f"/api/v1/datasets/{dataset['id']}/versions/1", params={"tag": "warranty"})
    cases = version.json()["cases"]
    assert {c["case_key"] for c in cases} == {"warranty-length", "battery-replacement"}
    assert cases[0]["relevant_document_ids"] is not None

    model = make_model("grounded", mode="expected")
    started = client.post(
        "/api/v1/runs",
        json={
            "project_id": project["id"],
            "dataset_id": dataset["id"],
            "model_config_ids": [model["id"]],
            "metrics": [
                {"name": "retrieval_recall_at_k", "config": {"k": 3}},
                {"name": "reciprocal_rank"},
                {"name": "llm_judge_groundedness", "config": JUDGE},
            ],
            "run_config": {"max_retries": 0, "retry_backoff_seconds": 0},
        },
    )
    assert started.status_code == 202, started.text
    run_id = started.json()["run_id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "completed"
    summary = run["models"][0]["metrics"]
    assert summary["retrieval_recall_at_k"]["scored_count"] == 6
    assert summary["retrieval_recall_at_k"]["not_applicable_count"] == 1
    assert summary["llm_judge_groundedness"]["scored_count"] == 7

    missed = client.get(
        f"/api/v1/runs/{run_id}/results",
        params={"metric": "reciprocal_rank", "max_score": 0},
    ).json()
    assert [r["case_key"] for r in missed["items"]] == ["battery-replacement"]

    exported = client.get(f"/api/v1/runs/{run_id}/report", params={"format": "csv"})
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows) == 7
    markdown = client.get(f"/api/v1/runs/{run_id}/report", params={"format": "markdown"}).text
    assert "llm_judge_groundedness" in markdown
