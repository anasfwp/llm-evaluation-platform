from __future__ import annotations

from fastapi.testclient import TestClient

from tests.integration.conftest import JsonDict, ModelFactory


def test_create_update_and_list_models(client: TestClient, project: JsonDict) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/models",
        json={
            "name": "fake-a",
            "provider": "fake",
            "model_id": "fake-v1",
            "parameters": {"mode": "constant", "constant_output": "hi"},
            "secret_reference": "SOME_API_KEY",
        },
    )
    assert response.status_code == 201, response.text
    model = response.json()
    assert model["secret_reference"] == "SOME_API_KEY"

    updated = client.patch(f"/api/v1/models/{model['id']}", json={"model_id": "fake-v2"})
    assert updated.status_code == 200
    assert updated.json()["model_id"] == "fake-v2"
    assert client.get(f"/api/v1/models/{model['id']}").json()["model_id"] == "fake-v2"

    listed = client.get(f"/api/v1/projects/{project['id']}/models").json()
    assert [m["name"] for m in listed["items"]] == ["fake-a"]


def test_unknown_provider_rejected(client: TestClient, project: JsonDict) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/models",
        json={"name": "x", "provider": "does-not-exist", "model_id": "m"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_invalid_provider_parameters_rejected(client: TestClient, project: JsonDict) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/models",
        json={"name": "x", "provider": "fake", "model_id": "m", "parameters": {"mode": "bogus"}},
    )
    assert response.status_code == 422


def test_secret_values_never_accepted(client: TestClient, project: JsonDict) -> None:
    response = client.post(
        f"/api/v1/projects/{project['id']}/models",
        json={
            "name": "leaky",
            "provider": "fake",
            "model_id": "m",
            "parameters": {"nested": {"api_key": "sk-test-1234567890abcdef"}},
        },
    )
    assert response.status_code == 422
    assert "sk-test-1234567890abcdef" not in response.text

    bad_reference = client.post(
        f"/api/v1/projects/{project['id']}/models",
        json={"name": "x", "provider": "fake", "model_id": "m", "secret_reference": "sk-abc"},
    )
    assert bad_reference.status_code == 422


def test_duplicate_model_name_conflicts(client: TestClient, make_model: ModelFactory) -> None:
    model = make_model("dup")
    response = client.post(
        f"/api/v1/projects/{model['project_id']}/models",
        json={"name": "dup", "provider": "fake", "model_id": "m"},
    )
    assert response.status_code == 409


def test_connectivity_check(client: TestClient, make_model: ModelFactory) -> None:
    ok = client.post(f"/api/v1/models/{make_model('good')['id']}/test")
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
    assert ok.json()["provider"] == "fake"

    failing = make_model(
        "bad", overrides={"connectivity-check": {"error": "authentication_failed"}}
    )
    response = client.post(f"/api/v1/models/{failing['id']}/test")
    assert response.status_code == 502
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == "authentication_failed"
