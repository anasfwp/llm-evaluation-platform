"""API integration fixtures.

Tests run against a throwaway SQLite file by default. Set ``TEST_DATABASE_URL``
to a disposable PostgreSQL database (CI does) to run the same tests there; every
table in that database is dropped and recreated per test.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.base import Base
from app.db.session import build_engine
from app.main import create_app

JsonDict = dict[str, Any]


@pytest.fixture
def database_url(tmp_path: Path) -> str:
    return os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{(tmp_path / 'test.db').as_posix()}"


@pytest.fixture
def settings(database_url: str) -> Settings:
    return Settings(
        _env_file=None,  # type: ignore[call-arg]
        app_env="test",
        log_level="WARNING",
        database_url=database_url,
        run_dispatcher="inline",
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    engine = build_engine(settings.database_url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    engine.dispose()
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client
    app.state.session_factory.kw["bind"].dispose()


class RecordingDispatcher:
    """Leaves runs queued so tests can observe and cancel them."""

    def __init__(self) -> None:
        self.dispatched: list[uuid.UUID] = []

    def dispatch(self, run_id: uuid.UUID) -> None:
        self.dispatched.append(run_id)


@pytest.fixture
def recording_dispatcher(client: TestClient) -> RecordingDispatcher:
    dispatcher = RecordingDispatcher()
    client.app.state.dispatcher = dispatcher  # type: ignore[attr-defined]
    return dispatcher


def sample_cases(count: int = 4) -> list[JsonDict]:
    cases: list[JsonDict] = [
        {
            "case_key": f"case-{i}",
            "input": {"question": f"question {i}"},
            "expected_output": f"answer {i}",
            "tags": ["even" if i % 2 == 0 else "odd"],
        }
        for i in range(count)
    ]
    cases.append(
        {"case_key": "open-ended", "input": {"question": "say hi"}, "expected_output": None}
    )
    return cases


@pytest.fixture
def project(client: TestClient) -> JsonDict:
    response = client.post("/api/v1/projects", json={"name": "test-project"})
    assert response.status_code == 201, response.text
    body: JsonDict = response.json()
    return body


@pytest.fixture
def dataset(client: TestClient, project: JsonDict) -> JsonDict:
    response = client.post(
        f"/api/v1/projects/{project['id']}/datasets",
        json={"name": "qa", "cases": sample_cases()},
    )
    assert response.status_code == 201, response.text
    body: JsonDict = response.json()
    return body


ModelFactory = Callable[..., JsonDict]


@pytest.fixture
def make_model(client: TestClient, project: JsonDict) -> ModelFactory:
    def factory(name: str = "fake-model", **parameters: Any) -> JsonDict:
        response = client.post(
            f"/api/v1/projects/{project['id']}/models",
            json={
                "name": name,
                "provider": "fake",
                "model_id": f"{name}-v1",
                "parameters": parameters,
            },
        )
        assert response.status_code == 201, response.text
        body: JsonDict = response.json()
        return body

    return factory
