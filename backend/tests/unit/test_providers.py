"""Provider adapters, exercised offline through mock HTTP transports."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import anthropic
import httpx
import httpx2
import pytest

from app.core.config import load_local_env
from app.domain.datasets import Dataset, EvaluationCase
from app.domain.models import ModelConfigSnapshot, ModelRequest, ProviderErrorCategory
from app.providers.anthropic_messages import AnthropicParameters, AnthropicProvider
from app.providers.base import ProviderError
from app.providers.http_errors import category_for_status, parse_retry_after
from app.providers.openai_compatible import (
    OpenAICompatibleParameters,
    OpenAICompatibleProvider,
    OpenAIProvider,
)
from app.providers.prompting import render_prompt
from app.providers.registry import PROVIDERS

REQUEST = ModelRequest(case_key="c1", input_data={"question": "Capital of France?"})
DATASET = Dataset(
    schema_version="1.0",
    name="d",
    cases=[EvaluationCase(case_key="c1", input={"question": "q"}, expected_output="Paris")],
)


def _snapshot(provider: str, model_id: str = "m", **fields: Any) -> ModelConfigSnapshot:
    return ModelConfigSnapshot(name="m1", provider=provider, model_id=model_id, **fields)


# --- prompting -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("input_data", "expected"),
    [
        ({"question": "Q?", "context": "c"}, "Q?"),
        ({"prompt": "P", "question": "Q"}, "P"),
        ({"text": "only value"}, "only value"),
        ({"a": 1, "b": "x"}, '{"a": 1, "b": "x"}'),
    ],
)
def test_default_prompt_rendering(input_data: dict[str, Any], expected: str) -> None:
    assert render_prompt(input_data, None) == expected


def test_template_substitutes_fields_without_evaluating_them() -> None:
    template = "Context: {{context}}\nQ: {{ question }} {{question.__class__}}"
    rendered = render_prompt({"context": ["a", "b"], "question": "Why?"}, template)
    # Only plain names are placeholders; anything else is left as literal text.
    assert rendered == 'Context: ["a", "b"]\nQ: Why? {{question.__class__}}'


def test_template_with_missing_field_is_an_invalid_request() -> None:
    with pytest.raises(ProviderError) as info:
        render_prompt({"question": "q"}, "{{question}} {{missing}}")
    assert info.value.category == ProviderErrorCategory.INVALID_REQUEST
    assert "missing" in info.value.message


# --- shared HTTP error handling ------------------------------------------------


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, ProviderErrorCategory.AUTHENTICATION_FAILED),
        (403, ProviderErrorCategory.AUTHENTICATION_FAILED),
        (429, ProviderErrorCategory.RATE_LIMITED),
        (408, ProviderErrorCategory.TIMEOUT),
        (504, ProviderErrorCategory.TIMEOUT),
        (500, ProviderErrorCategory.PROVIDER_UNAVAILABLE),
        (529, ProviderErrorCategory.PROVIDER_UNAVAILABLE),
        (400, ProviderErrorCategory.INVALID_REQUEST),
        (404, ProviderErrorCategory.INVALID_REQUEST),
        (402, ProviderErrorCategory.UNKNOWN),
    ],
)
def test_status_mapping(status: int, category: ProviderErrorCategory) -> None:
    assert category_for_status(status) == category


def test_retry_after_parsing() -> None:
    now = datetime(2026, 10, 27, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("7") == 7.0
    assert parse_retry_after("Tue, 27 Oct 2026 12:00:10 GMT", now=now) == 10.0
    assert parse_retry_after("100000") == 60.0  # capped
    assert parse_retry_after("-5") == 0.0
    assert parse_retry_after("soon") is None
    assert parse_retry_after(None) is None


def test_registry_lists_all_providers() -> None:
    assert set(PROVIDERS) == {"fake", "anthropic", "openai", "openai_compatible"}


# --- Anthropic -----------------------------------------------------------------

Handler = Callable[[httpx2.Request], httpx2.Response]


def _anthropic(handler: Handler, **params: Any) -> AnthropicProvider:
    client = anthropic.AsyncAnthropic(
        api_key="test-key",
        max_retries=0,
        http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(handler)),
    )
    return AnthropicProvider(
        AnthropicParameters.model_validate(params), client, secret_env="ANTHROPIC_API_KEY"
    )


def _message(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "sig"},
            {"type": "text", "text": "Paris"},
        ],
        "stop_reason": "end_turn",
        "stop_sequence": None,
        "usage": {
            "input_tokens": 12,
            "output_tokens": 30,
            "output_tokens_details": {"thinking_tokens": 20},
        },
    }
    body.update(overrides)
    return body


def _generate(adapter: Any, model_id: str = "claude-opus-5-5") -> Any:
    async def call() -> Any:
        try:
            return await adapter.generate(
                request=REQUEST, model_config=_snapshot("anthropic", model_id), timeout_seconds=5
            )
        finally:
            await adapter.aclose()

    return asyncio.run(call())


def test_anthropic_success_normalizes_text_and_usage() -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append(json.loads(request.content))
        assert request.headers["anthropic-version"] == "2026-10-21"
        return httpx2.Response(200, headers={"request-id": "req_abc"}, json=_message())

    response = _generate(
        _anthropic(handler, system_prompt="Answer briefly.", effort="low", max_tokens=256)
    )
    assert response.output_text == "Paris"  # thinking blocks are not part of the answer
    assert (response.input_tokens, response.output_tokens) == (12, 30)
    assert response.provider == "anthropic"
    assert response.provider_request_id == "req_abc"
    assert response.finish_reason == "end_turn"
    assert response.raw_metadata["thinking_tokens"] == 20
    body = sent[0]
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == 256
    assert body["system"] == "Answer briefly."
    assert body["output_config"] == {"effort": "low"}
    assert body["messages"] == [{"role": "user", "content": "Capital of France?"}]
    # API version 2026-10-21 rejects sampling parameters, so they are never sent.
    assert not {"temperature", "top_p", "top_k"} & set(body)


def test_anthropic_refusal_is_returned_not_retried() -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            200,
            json=_message(
                content=[],
                stop_reason="refusal",
                stop_details={"type": "refusal", "category": "cyber", "explanation": None},
            ),
        )

    response = _generate(_anthropic(handler))
    assert response.output_text == ""
    assert response.finish_reason == "refusal"
    assert response.raw_metadata["refusal_category"] == "cyber"


@pytest.mark.parametrize(
    ("status", "error_type", "category"),
    [
        (429, "rate_limit_error", ProviderErrorCategory.RATE_LIMITED),
        (529, "overloaded_error", ProviderErrorCategory.PROVIDER_UNAVAILABLE),
        (401, "authentication_error", ProviderErrorCategory.AUTHENTICATION_FAILED),
        (400, "invalid_request_error", ProviderErrorCategory.INVALID_REQUEST),
        (404, "not_found_error", ProviderErrorCategory.INVALID_REQUEST),
    ],
)
def test_anthropic_errors_are_categorized(
    status: int, error_type: str, category: ProviderErrorCategory
) -> None:
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(
            status,
            headers={"retry-after": "3"},
            json={"type": "error", "error": {"type": error_type, "message": "details"}},
        )

    with pytest.raises(ProviderError) as info:
        _generate(_anthropic(handler))
    assert info.value.category == category
    assert error_type in info.value.message
    assert info.value.retry_after_seconds == 3.0


def test_anthropic_connection_failure_and_timeout() -> None:
    def refused(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused", request=request)

    def slow(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as info:
        _generate(_anthropic(refused))
    assert info.value.category == ProviderErrorCategory.PROVIDER_UNAVAILABLE
    with pytest.raises(ProviderError) as info:
        _generate(_anthropic(slow))
    assert info.value.category == ProviderErrorCategory.TIMEOUT


def test_anthropic_without_key_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MY_ANTHROPIC_KEY", raising=False)
    adapter = AnthropicProvider.from_config(
        _snapshot("anthropic", secret_reference="MY_ANTHROPIC_KEY"), dataset=DATASET
    )
    with pytest.raises(ProviderError) as info:
        _generate(adapter)
    assert info.value.category == ProviderErrorCategory.AUTHENTICATION_FAILED
    assert "MY_ANTHROPIC_KEY" in info.value.message


def test_anthropic_rejects_sampling_parameters_in_config() -> None:
    with pytest.raises(ValueError, match="temperature"):
        AnthropicParameters.model_validate({"temperature": 0})


# --- OpenAI-compatible ---------------------------------------------------------

OpenAIHandler = Callable[[httpx.Request], httpx.Response]


def _compatible(
    handler: OpenAIHandler, *, api_key: str | None = "test-key", **params: Any
) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        OpenAICompatibleParameters.model_validate(params),
        base_url="http://llm.internal/v1",
        api_key=api_key,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=False),
    )


def _run(adapter: Any, provider: str = "openai_compatible") -> Any:
    async def call() -> Any:
        try:
            return await adapter.generate(
                request=REQUEST, model_config=_snapshot(provider, "local-model"), timeout_seconds=5
            )
        finally:
            await adapter.aclose()

    return asyncio.run(call())


def test_compatible_success() -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-1",
                "model": "local-model",
                "choices": [
                    {"message": {"role": "assistant", "content": "Paris"}, "finish_reason": "stop"}
                ],
                "usage": {"prompt_tokens": 9, "completion_tokens": 1},
            },
        )

    response = _run(_compatible(handler, temperature=0, seed=7, system_prompt="Be brief."))
    assert response.output_text == "Paris"
    assert (response.input_tokens, response.output_tokens) == (9, 1)
    assert response.provider_request_id == "chatcmpl-1"
    request = sent[0]
    assert str(request.url) == "http://llm.internal/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer test-key"
    body = json.loads(request.content)
    assert body["temperature"] == 0
    assert body["seed"] == 7
    assert body["messages"][0] == {"role": "system", "content": "Be brief."}
    assert "max_tokens" not in body  # unset options are omitted


def test_compatible_without_key_sends_no_auth_and_tolerates_missing_usage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

    response = _run(_compatible(handler, api_key=None))
    assert response.output_text == ""
    assert response.input_tokens is None


@pytest.mark.parametrize(
    ("response", "category"),
    [
        (httpx.Response(429, headers={"retry-after": "2"}), ProviderErrorCategory.RATE_LIMITED),
        (httpx.Response(503), ProviderErrorCategory.PROVIDER_UNAVAILABLE),
        (
            httpx.Response(401, json={"error": {"type": "invalid_api_key"}}),
            ProviderErrorCategory.AUTHENTICATION_FAILED,
        ),
        (
            httpx.Response(302, headers={"location": "http://elsewhere"}),
            ProviderErrorCategory.INVALID_REQUEST,
        ),
        (httpx.Response(200, text="not json"), ProviderErrorCategory.UNKNOWN),
        (httpx.Response(200, json={"choices": []}), ProviderErrorCategory.UNKNOWN),
    ],
)
def test_compatible_errors(response: httpx.Response, category: ProviderErrorCategory) -> None:
    with pytest.raises(ProviderError) as info:
        _run(_compatible(lambda request: response))
    assert info.value.category == category


def test_compatible_network_errors() -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderError) as info:
        _run(_compatible(refused))
    assert info.value.category == ProviderErrorCategory.PROVIDER_UNAVAILABLE
    with pytest.raises(ProviderError) as info:
        _run(_compatible(slow))
    assert info.value.category == ProviderErrorCategory.TIMEOUT


@pytest.mark.parametrize(
    ("value", "message"),
    [
        (None, "base URL is not configured"),
        ("ftp://host/v1", "must be an http(s) URL"),
        ("http://user:pw@host/v1", "must not contain credentials"),
    ],
)
def test_compatible_base_url_validation(
    monkeypatch: pytest.MonkeyPatch, value: str | None, message: str
) -> None:
    if value is None:
        monkeypatch.delenv("OPENAI_COMPATIBLE_BASE_URL", raising=False)
    else:
        monkeypatch.setenv("OPENAI_COMPATIBLE_BASE_URL", value)
    adapter = OpenAICompatibleProvider.from_config(_snapshot("openai_compatible"), dataset=DATASET)
    with pytest.raises(ProviderError) as info:
        _run(adapter)
    assert info.value.category == ProviderErrorCategory.INVALID_REQUEST
    assert message in info.value.message


def test_openai_requires_key_and_uses_fixed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    adapter = OpenAIProvider.from_config(_snapshot("openai"), dataset=DATASET)
    with pytest.raises(ProviderError) as info:
        _run(adapter, "openai")
    assert info.value.category == ProviderErrorCategory.AUTHENTICATION_FAILED
    assert "OPENAI_API_KEY" in info.value.message
    with pytest.raises(ValueError, match="base_url_env"):
        OpenAIProvider.Parameters.model_validate({"base_url_env": "X"})


def test_env_references_for_allowlisting() -> None:
    assert AnthropicProvider.env_references({}, None) == {"secret_reference": "ANTHROPIC_API_KEY"}
    assert OpenAIProvider.env_references({}, "TEAM_OPENAI_KEY") == {
        "secret_reference": "TEAM_OPENAI_KEY"
    }
    assert OpenAICompatibleProvider.env_references({"base_url_env": "VLLM_URL"}, None) == {
        "secret_reference": "OPENAI_COMPATIBLE_API_KEY",
        "parameters.base_url_env": "VLLM_URL",
    }
    assert PROVIDERS["fake"].env_references({}, None) == {}


def test_compatible_reads_list_wrapped_errors() -> None:
    # Gemini's OpenAI-compatible endpoint returns [{"error": {...}}].
    body = [{"error": {"code": 404, "message": "model retired", "status": "NOT_FOUND"}}]
    with pytest.raises(ProviderError) as info:
        _run(_compatible(lambda request: httpx.Response(404, json=body)))
    assert info.value.category == ProviderErrorCategory.INVALID_REQUEST
    assert info.value.message == "provider returned HTTP 404 (NOT_FOUND)"


def test_load_local_env_fills_only_unset_variables(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / ".env").write_text("EVAL_TEST_NEW=from-file\nEVAL_TEST_SET=from-file\n")
    nested = tmp_path / "backend"
    nested.mkdir()
    monkeypatch.chdir(nested)  # found by searching up from the working directory
    monkeypatch.delenv("EVAL_TEST_NEW", raising=False)
    monkeypatch.setenv("EVAL_TEST_SET", "from-shell")
    load_local_env()
    assert os.environ["EVAL_TEST_NEW"] == "from-file"
    assert os.environ["EVAL_TEST_SET"] == "from-shell"
    monkeypatch.delenv("EVAL_TEST_NEW")


def test_compatible_reads_google_retry_delay() -> None:
    body = [
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {"@type": "type.googleapis.com/google.rpc.Help", "links": []},
                    {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "50s"},
                ],
            }
        }
    ]
    with pytest.raises(ProviderError) as info:
        _run(_compatible(lambda request: httpx.Response(429, json=body)))
    assert info.value.category == ProviderErrorCategory.RATE_LIMITED
    assert info.value.retry_after_seconds == 50.0
