from __future__ import annotations

import asyncio
import re
import time
import uuid
from typing import Any

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.core.errors import (
    ConflictError,
    InvalidRequestError,
    Issue,
    NotFoundError,
    issues_from_validation_error,
)
from app.db.models import ModelConfig
from app.db.repositories import model_configs as repo
from app.domain.datasets import Dataset, EvaluationCase
from app.domain.models import ModelConfigSnapshot, ModelRequest
from app.providers.base import ProviderError
from app.providers.registry import get_provider
from app.schemas.model_config import ConnectivityResult, ModelConfigCreate, ModelConfigUpdate
from app.services.project_service import require_active_project
from app.utils.redaction import safe_error_message

# Parameters are stored and returned verbatim, so they must never carry credentials.
_SECRET_LIKE_KEY = re.compile(r"(api[_-]?key|secret|token|password|authorization|credential)", re.I)
_PROBE_CASE_KEY = "connectivity-check"


def _secret_like_keys(value: Any, path: str = "parameters") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, inner in value.items():
            location = f"{path}.{key}"
            if _SECRET_LIKE_KEY.search(str(key)):
                found.append(location)
            found.extend(_secret_like_keys(inner, location))
    elif isinstance(value, list):
        for index, inner in enumerate(value):
            found.extend(_secret_like_keys(inner, f"{path}[{index}]"))
    return found


def check_env_references(
    provider: str,
    parameters: dict[str, Any],
    secret_reference: str | None,
    allowed_env: frozenset[str],
) -> None:
    """Reject configurations that would make the worker read non-allowlisted variables."""
    factory = get_provider(provider)
    references = factory.env_references(parameters, secret_reference)
    denied = [
        Issue(location, f"environment variable '{name}' is not in PROVIDER_ENV_ALLOWLIST")
        for location, name in references.items()
        if name not in allowed_env
    ]
    if denied:
        raise InvalidRequestError("model configuration references disallowed variables", denied)


def _validate(
    provider: str,
    parameters: dict[str, Any],
    secret_reference: str | None,
    allowed_env: frozenset[str],
) -> None:
    try:
        factory = get_provider(provider)
    except KeyError as exc:
        raise InvalidRequestError(str(exc.args[0]), [Issue("provider", str(exc.args[0]))]) from None
    secret_keys = _secret_like_keys(parameters)
    if secret_keys:
        message = "credentials must not be stored in parameters; use secret_reference"
        raise InvalidRequestError(message, [Issue(loc, message) for loc in secret_keys])
    try:
        factory.Parameters.model_validate(parameters)
    except ValidationError as exc:
        raise InvalidRequestError(
            "invalid provider parameters", issues_from_validation_error(exc, prefix="parameters")
        ) from None
    check_env_references(provider, parameters, secret_reference, allowed_env)


def to_snapshot(config: ModelConfig) -> ModelConfigSnapshot:
    return ModelConfigSnapshot(
        name=config.name,
        provider=config.provider,
        model_id=config.model_id,
        parameters=config.parameters_json,
        timeout_seconds=config.timeout_seconds,
        max_concurrency=config.max_concurrency,
        secret_reference=config.secret_reference,
    )


def create_model_config(
    session: Session,
    project_id: uuid.UUID,
    data: ModelConfigCreate,
    *,
    allowed_env: frozenset[str],
) -> ModelConfig:
    require_active_project(session, project_id)
    if repo.get_by_name(session, project_id, data.name) is not None:
        raise ConflictError(f"a model configuration named '{data.name}' already exists")
    _validate(data.provider, data.parameters, data.secret_reference, allowed_env)
    config = ModelConfig(
        project_id=project_id,
        name=data.name,
        provider=data.provider,
        model_id=data.model_id,
        parameters_json=data.parameters,
        timeout_seconds=data.timeout_seconds,
        max_concurrency=data.max_concurrency,
        secret_reference=data.secret_reference,
    )
    session.add(config)
    session.commit()
    return config


def get_model_config(session: Session, model_config_id: uuid.UUID) -> ModelConfig:
    config = repo.get(session, model_config_id)
    if config is None:
        raise NotFoundError(f"model configuration {model_config_id} not found")
    return config


def list_model_configs(
    session: Session, project_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[ModelConfig], int]:
    require_active_project(session, project_id)
    return repo.list_for_project(session, project_id, limit=limit, offset=offset)


def update_model_config(
    session: Session,
    model_config_id: uuid.UUID,
    data: ModelConfigUpdate,
    *,
    allowed_env: frozenset[str],
) -> ModelConfig:
    config = get_model_config(session, model_config_id)
    parameters = data.parameters if data.parameters is not None else config.parameters_json
    secret_reference = (
        data.secret_reference
        if "secret_reference" in data.model_fields_set
        else config.secret_reference
    )
    _validate(config.provider, parameters, secret_reference, allowed_env)
    if data.parameters is not None:
        config.parameters_json = data.parameters
    if data.model_id is not None:
        config.model_id = data.model_id
    # Explicit nulls clear optional settings; omitted fields are left unchanged.
    for field in ("timeout_seconds", "max_concurrency", "secret_reference"):
        if field in data.model_fields_set:
            setattr(config, field, getattr(data, field))
    session.commit()
    return config


def test_connectivity(config: ModelConfig, *, timeout_seconds: float = 15) -> ConnectivityResult:
    """Send one tiny probe request. Note: for paid providers this makes a billable call."""
    snapshot = to_snapshot(config)
    probe = Dataset(
        schema_version="1.0",
        name="connectivity-probe",
        cases=[
            EvaluationCase(
                case_key=_PROBE_CASE_KEY, input={"question": "Reply with OK."}, expected_output="OK"
            )
        ],
    )
    adapter = get_provider(config.provider).from_config(snapshot, dataset=probe)
    timeout = min(snapshot.timeout_seconds or timeout_seconds, timeout_seconds)
    request = ModelRequest(case_key=_PROBE_CASE_KEY, input_data=probe.cases[0].input)
    start = time.perf_counter()

    async def call() -> None:
        try:
            await asyncio.wait_for(
                adapter.generate(request=request, model_config=snapshot, timeout_seconds=timeout),
                timeout=timeout,
            )
        finally:
            await adapter.aclose()

    try:
        asyncio.run(call())
    except TimeoutError:
        return ConnectivityResult(
            ok=False, provider=config.provider, latency_ms=None, error_code="timeout"
        )
    except ProviderError as exc:
        return ConnectivityResult(
            ok=False,
            provider=config.provider,
            latency_ms=None,
            error_code=str(exc.category),
            error_message=safe_error_message(exc.message),
        )
    return ConnectivityResult(
        ok=True, provider=config.provider, latency_ms=(time.perf_counter() - start) * 1000
    )
