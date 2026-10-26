from __future__ import annotations

import uuid

from fastapi.testclient import TestClient


def test_health_endpoints(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    ready = client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"] == {"database": "ok"}


def test_project_crud_and_archive(client: TestClient) -> None:
    created = client.post(
        "/api/v1/projects", json={"name": "alpha", "description": "first", "settings": {"a": 1}}
    )
    assert created.status_code == 201
    project = created.json()
    assert project["name"] == "alpha"
    assert project["settings"] == {"a": 1}
    assert project["archived_at"] is None

    fetched = client.get(f"/api/v1/projects/{project['id']}")
    assert fetched.json()["id"] == project["id"]

    updated = client.patch(f"/api/v1/projects/{project['id']}", json={"description": "changed"})
    assert updated.status_code == 200
    assert updated.json()["description"] == "changed"
    assert updated.json()["name"] == "alpha"

    listed = client.get("/api/v1/projects").json()
    assert listed["total"] == 1
    assert [p["name"] for p in listed["items"]] == ["alpha"]

    assert client.delete(f"/api/v1/projects/{project['id']}").status_code == 204
    assert client.get("/api/v1/projects").json()["total"] == 0
    archived = client.get("/api/v1/projects", params={"include_archived": True}).json()
    assert archived["items"][0]["archived_at"] is not None
    # Archived projects stay readable.
    assert client.get(f"/api/v1/projects/{project['id']}").status_code == 200


def test_duplicate_project_name_conflicts(client: TestClient) -> None:
    assert client.post("/api/v1/projects", json={"name": "dup"}).status_code == 201
    response = client.post("/api/v1/projects", json={"name": "dup"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONFLICT"


def test_pagination(client: TestClient) -> None:
    for i in range(5):
        client.post("/api/v1/projects", json={"name": f"p{i}"})
    page = client.get("/api/v1/projects", params={"limit": 2, "offset": 2}).json()
    assert page["total"] == 5
    assert page["limit"] == 2
    assert page["offset"] == 2
    assert len(page["items"]) == 2
    assert client.get("/api/v1/projects", params={"limit": 0}).status_code == 422


def test_error_envelope_for_missing_project(client: TestClient) -> None:
    response = client.get(f"/api/v1/projects/{uuid.uuid4()}", headers={"X-Request-ID": "abc-123"})
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == "abc-123"
    assert response.headers["X-Request-ID"] == "abc-123"


def test_validation_error_envelope(client: TestClient) -> None:
    response = client.post("/api/v1/projects", json={"name": "", "unexpected": True})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    fields = {detail["field"] for detail in error["details"]}
    assert "body.name" in fields
    assert "body.unexpected" in fields
    assert error["request_id"].startswith("req_")


def test_unknown_route_uses_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_oversized_body_rejected(client: TestClient) -> None:
    limit = client.app.state.settings.max_request_bytes  # type: ignore[attr-defined]
    response = client.post(
        "/api/v1/projects",
        content=b"x" * (limit + 1),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
