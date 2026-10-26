from __future__ import annotations

import json
import uuid

from fastapi.testclient import TestClient

from tests.integration.conftest import JsonDict, sample_cases


def test_create_and_read_dataset(client: TestClient, dataset: JsonDict) -> None:
    assert dataset["current_version"] == 1
    assert dataset["case_count"] == 5

    fetched = client.get(f"/api/v1/datasets/{dataset['id']}").json()
    assert fetched["name"] == "qa"

    listed = client.get(f"/api/v1/projects/{dataset['project_id']}/datasets").json()
    assert listed["total"] == 1
    assert listed["items"][0]["case_count"] == 5


def test_version_detail_filters_cases(client: TestClient, dataset: JsonDict) -> None:
    url = f"/api/v1/datasets/{dataset['id']}/versions/1"
    detail = client.get(url).json()
    assert detail["case_count"] == 5
    assert detail["content_hash"].startswith("sha256:")
    assert [c["case_key"] for c in detail["cases"]][:2] == ["case-0", "case-1"]

    even = client.get(url, params={"tag": "even"}).json()
    assert even["matching_cases"] == 2
    assert {c["case_key"] for c in even["cases"]} == {"case-0", "case-2"}

    search = client.get(url, params={"q": "open"}).json()
    assert [c["case_key"] for c in search["cases"]] == ["open-ended"]

    paged = client.get(url, params={"limit": 2, "offset": 1}).json()
    assert [c["case_key"] for c in paged["cases"]] == ["case-1", "case-2"]
    assert paged["matching_cases"] == 5


def test_new_version_keeps_old_one(client: TestClient, dataset: JsonDict) -> None:
    response = client.post(
        f"/api/v1/datasets/{dataset['id']}/versions", json={"cases": sample_cases(2)}
    )
    assert response.status_code == 201
    assert response.json()["version_number"] == 2

    versions = client.get(f"/api/v1/datasets/{dataset['id']}/versions").json()
    assert [v["version_number"] for v in versions] == [1, 2]
    assert versions[0]["content_hash"] != versions[1]["content_hash"]
    assert client.get(f"/api/v1/datasets/{dataset['id']}").json()["case_count"] == 3
    assert client.get(f"/api/v1/datasets/{dataset['id']}/versions/1").json()["case_count"] == 5
    assert client.get(f"/api/v1/datasets/{dataset['id']}/versions/9").status_code == 404


def test_rename_dataset(client: TestClient, dataset: JsonDict) -> None:
    response = client.patch(f"/api/v1/datasets/{dataset['id']}", json={"name": "renamed"})
    assert response.status_code == 200
    assert response.json()["name"] == "renamed"


def test_duplicate_case_keys_rejected(client: TestClient, project: JsonDict) -> None:
    case = {"case_key": "same", "input": {"q": "x"}, "expected_output": "y"}
    response = client.post(
        f"/api/v1/projects/{project['id']}/datasets", json={"name": "bad", "cases": [case, case]}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_dataset_for_unknown_project(client: TestClient) -> None:
    response = client.post(
        f"/api/v1/projects/{uuid.uuid4()}/datasets", json={"name": "x", "cases": sample_cases(1)}
    )
    assert response.status_code == 404


def test_import_jsonl_and_export_round_trip(client: TestClient, project: JsonDict) -> None:
    lines = "\n".join(json.dumps(case) for case in sample_cases(3))
    imported = client.post(
        "/api/v1/datasets/import",
        data={"project_id": project["id"], "name": "imported"},
        files={"file": ("cases.jsonl", lines.encode("utf-8"), "application/x-ndjson")},
    )
    assert imported.status_code == 201, imported.text
    dataset = imported.json()
    assert dataset["name"] == "imported"
    assert dataset["case_count"] == 4

    exported = client.get(f"/api/v1/datasets/{dataset['id']}/export", params={"format": "jsonl"})
    assert exported.status_code == 200
    assert "attachment" in exported.headers["content-disposition"]
    rows = [json.loads(line) for line in exported.text.splitlines() if line.strip()]
    assert [row["case_key"] for row in rows] == [c["case_key"] for c in sample_cases(3)]

    as_json = client.get(
        f"/api/v1/datasets/{dataset['id']}/export", params={"format": "json", "version": 1}
    ).json()
    assert as_json["name"] == "imported"
    assert len(as_json["cases"]) == 4

    # Re-importing the exported JSON yields identical cases (the hash also covers the name).
    reimported = client.post(
        "/api/v1/datasets/import",
        data={"project_id": project["id"], "name": "reimported"},
        files={"file": ("cases.json", json.dumps(as_json).encode("utf-8"), "application/json")},
    ).json()
    round_trip = client.get(
        f"/api/v1/datasets/{reimported['id']}/export", params={"format": "json"}
    ).json()
    assert round_trip["cases"] == as_json["cases"]


def test_import_rejects_invalid_files(client: TestClient, project: JsonDict) -> None:
    broken = client.post(
        "/api/v1/datasets/import",
        data={"project_id": project["id"]},
        files={"file": ("cases.json", b"{not json", "application/json")},
    )
    assert broken.status_code == 422
    assert broken.json()["error"]["code"] == "VALIDATION_ERROR"

    unsupported = client.post(
        "/api/v1/datasets/import",
        data={"project_id": project["id"]},
        files={"file": ("cases.csv", b"a,b", "text/csv")},
    )
    assert unsupported.status_code == 422
