"""OpenAI-compatible Chat Completions adapters.

``openai_compatible`` targets any server that implements ``POST
{base_url}/chat/completions`` (vLLM, Ollama, LM Studio, gateways, ...).
``openai`` is the same adapter with OpenAI's fixed base URL.

The base URL is read from an environment variable chosen by the operator
(``base_url_env``), never from a value stored in the model configuration, so
API users cannot point the worker, and its credentials, at arbitrary hosts.
Redirects are not followed.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, ClassVar, Self
from urllib.parse import urlsplit

import httpx
from pydantic import Field

from app.domain.datasets import Dataset
from app.domain.models import (
    SECRET_REFERENCE_PATTERN,
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.providers.base import BaseProvider, ProviderError
from app.providers.credentials import read_env
from app.providers.http_errors import category_for_status, parse_retry_after
from app.providers.prompting import PromptParameters, render_prompt

DEFAULT_BASE_URL_ENV = "OPENAI_COMPATIBLE_BASE_URL"


class ChatCompletionsParameters(PromptParameters):
    max_tokens: int | None = Field(default=None, ge=1, le=200_000)
    temperature: float | None = Field(default=None, ge=0, le=2)
    top_p: float | None = Field(default=None, gt=0, le=1)
    seed: int | None = None
    stop: list[str] = Field(default_factory=list, max_length=4)


class OpenAICompatibleParameters(ChatCompletionsParameters):
    # Name of the environment variable holding the base URL, e.g. http://localhost:11434/v1
    base_url_env: str = Field(default=DEFAULT_BASE_URL_ENV, pattern=SECRET_REFERENCE_PATTERN)


class OpenAICompatibleProvider(BaseProvider):
    provider_name: ClassVar[str] = "openai_compatible"
    Parameters: ClassVar[type[ChatCompletionsParameters]] = OpenAICompatibleParameters
    default_secret_env: ClassVar[str | None] = "OPENAI_COMPATIBLE_API_KEY"
    # When set, the base URL is fixed and ``base_url_env`` is not used.
    fixed_base_url: ClassVar[str | None] = None
    # Local servers often need no key; hosted APIs do.
    requires_api_key: ClassVar[bool] = False

    def __init__(
        self,
        parameters: ChatCompletionsParameters,
        *,
        base_url: str | None,
        api_key: str | None,
        config_error: ProviderError | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._params = parameters
        self._base_url = base_url
        self._api_key = api_key
        # Set when the configuration cannot work; every call then raises it.
        self._config_error = config_error
        self._client = client or httpx.AsyncClient(follow_redirects=False)

    @classmethod
    def from_config(cls, model_config: ModelConfigSnapshot, *, dataset: Dataset) -> Self:
        params = cls.Parameters.model_validate(model_config.parameters)
        secret_env = model_config.secret_reference or cls.default_secret_env
        api_key = read_env(secret_env)
        base_url, error = cls._resolve_base_url(params)
        if error is None and api_key is None and cls.requires_api_key:
            error = ProviderError(
                ProviderErrorCategory.AUTHENTICATION_FAILED,
                f"API key is not configured: set {secret_env}",
            )
        return cls(params, base_url=base_url, api_key=api_key, config_error=error)

    @classmethod
    def _resolve_base_url(
        cls, params: ChatCompletionsParameters
    ) -> tuple[str | None, ProviderError | None]:
        if cls.fixed_base_url is not None:
            return cls.fixed_base_url, None
        return resolve_base_url(getattr(params, "base_url_env", DEFAULT_BASE_URL_ENV))

    @classmethod
    def env_references(
        cls, parameters: Mapping[str, Any], secret_reference: str | None
    ) -> dict[str, str]:
        references = super().env_references(parameters, secret_reference)
        if cls.fixed_base_url is None:
            base_url_env = parameters.get("base_url_env", DEFAULT_BASE_URL_ENV)
            if isinstance(base_url_env, str):
                references["parameters.base_url_env"] = base_url_env
        return references

    async def generate(
        self,
        *,
        request: ModelRequest,
        model_config: ModelConfigSnapshot,
        timeout_seconds: float,
    ) -> NormalizedModelResponse:
        if self._config_error is not None:
            raise self._config_error
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        try:
            response = await self._client.post(
                f"{self._base_url}/chat/completions",
                json=self._body(request, model_config),
                headers=headers,
                timeout=timeout_seconds,
            )
        except httpx.TimeoutException:
            raise ProviderError(ProviderErrorCategory.TIMEOUT, "request timed out") from None
        except httpx.HTTPError as exc:
            raise ProviderError(
                ProviderErrorCategory.PROVIDER_UNAVAILABLE,
                f"could not reach the provider ({type(exc).__name__})",
            ) from None

        if response.status_code >= 400:
            raise status_error(response)
        if response.status_code >= 300:
            raise ProviderError(
                ProviderErrorCategory.INVALID_REQUEST,
                f"provider answered with a redirect (HTTP {response.status_code}); "
                "redirects are not followed - check the base URL",
            )
        return self._normalize(response, model_config)

    def _body(self, request: ModelRequest, model_config: ModelConfigSnapshot) -> dict[str, Any]:
        params = self._params
        messages: list[dict[str, str]] = []
        if params.system_prompt:
            messages.append({"role": "system", "content": params.system_prompt})
        messages.append(
            {"role": "user", "content": render_prompt(request.input_data, params.prompt_template)}
        )
        body: dict[str, Any] = {"model": model_config.model_id, "messages": messages}
        optional = {
            "max_tokens": params.max_tokens,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "seed": params.seed,
            "stop": params.stop or None,
        }
        body.update({key: value for key, value in optional.items() if value is not None})
        return body

    def _normalize(
        self, response: httpx.Response, model_config: ModelConfigSnapshot
    ) -> NormalizedModelResponse:
        try:
            data = response.json()
            choice = data["choices"][0]
            content = choice["message"].get("content")
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise ProviderError(
                ProviderErrorCategory.UNKNOWN, "unexpected response shape from provider"
            ) from None

        usage = data.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        return NormalizedModelResponse(
            output_text=_content_text(content),
            provider=self.provider_name,
            model_id=model_config.model_id,
            input_tokens=_int_or_none(usage.get("prompt_tokens")),
            output_tokens=_int_or_none(usage.get("completion_tokens")),
            provider_request_id=response.headers.get("x-request-id") or data.get("id"),
            finish_reason=choice.get("finish_reason"),
            raw_metadata={"served_model": data.get("model")},
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class OpenAIProvider(OpenAICompatibleProvider):
    provider_name: ClassVar[str] = "openai"
    Parameters: ClassVar[type[ChatCompletionsParameters]] = ChatCompletionsParameters
    default_secret_env: ClassVar[str | None] = "OPENAI_API_KEY"
    fixed_base_url: ClassVar[str | None] = "https://api.openai.com/v1"
    requires_api_key: ClassVar[bool] = True


def _config_error(message: str) -> ProviderError:
    return ProviderError(ProviderErrorCategory.INVALID_REQUEST, message)


def resolve_base_url(env_name: str) -> tuple[str | None, ProviderError | None]:
    """Read and validate a base URL from the named environment variable."""
    raw = read_env(env_name)
    if raw is None:
        return None, _config_error(f"base URL is not configured: set {env_name}")
    parts = urlsplit(raw.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None, _config_error(f"{env_name} must be an http(s) URL")
    if parts.username or parts.password:
        return None, _config_error(f"{env_name} must not contain credentials")
    return raw.strip().rstrip("/"), None


def status_error(response: httpx.Response) -> ProviderError:
    detail = ""
    retry_after = parse_retry_after(response.headers.get("retry-after"))
    try:
        body = response.json()
        if isinstance(body, list) and body:  # Gemini wraps the error object in a list
            body = body[0]
        error = body.get("error")
        if isinstance(error, dict):
            kind = error.get("type") or error.get("status") or error.get("code")
            detail = f" ({kind})" if isinstance(kind, str) else ""
            if retry_after is None:
                retry_after = _google_retry_delay(error)
    except (ValueError, AttributeError):
        pass
    return ProviderError(
        category_for_status(response.status_code),
        f"provider returned HTTP {response.status_code}{detail}",
        retry_after_seconds=retry_after,
    )


def _google_retry_delay(error: dict[str, Any]) -> float | None:
    """Google APIs put the wait in a ``google.rpc.RetryInfo`` detail (e.g. ``"50s"``)."""
    details = error.get("details")
    if not isinstance(details, list):
        return None
    for item in details:
        if isinstance(item, dict) and str(item.get("@type", "")).endswith("google.rpc.RetryInfo"):
            delay = item.get("retryDelay")
            if isinstance(delay, str) and delay.endswith("s"):
                return parse_retry_after(delay[:-1])
    return None


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(part.get("text", ""))
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        )
    return ""


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
