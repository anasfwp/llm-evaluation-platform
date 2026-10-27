"""Anthropic Messages API adapter (hosted provider), built on the official ``anthropic`` SDK.

Notes for evaluation use:

- The SDK's own retries are disabled; the engine applies the run's bounded
  retry policy so every attempt is counted in the case result.
- The API key is always passed explicitly from the configured environment
  variable. The SDK would otherwise fall back to other local credentials
  (profiles, auth tokens), which would make runs depend on the machine.
- API version 2026-10-21 (sent by this SDK) rejects ``temperature``,
  ``top_p`` and ``top_k``, so they are not offered. ``effort`` is the
  supported control over reasoning depth and token spend.
- Only ``text`` blocks form the answer. Thinking tokens are billed as output
  and are included in ``output_tokens``; the count is kept in metadata.
- A ``refusal`` stop reason is returned as a normal response with that
  finish reason, so it is visible in results instead of being retried.
"""

from __future__ import annotations

from typing import Any, ClassVar, Literal, Self

import anthropic
from pydantic import Field

from app.domain.datasets import Dataset
from app.domain.models import (
    ModelConfigSnapshot,
    ModelRequest,
    NormalizedModelResponse,
    ProviderErrorCategory,
)
from app.providers.base import BaseProvider, ProviderError
from app.providers.credentials import read_env
from app.providers.http_errors import category_for_status, parse_retry_after
from app.providers.prompting import PromptParameters, render_prompt


class AnthropicParameters(PromptParameters):
    max_tokens: int = Field(default=16_000, ge=1, le=128_000)
    effort: Literal["low", "medium", "high", "xhigh", "max"] | None = None
    stop_sequences: list[str] = Field(default_factory=list, max_length=8)


class AnthropicProvider(BaseProvider):
    provider_name: ClassVar[str] = "anthropic"
    Parameters: ClassVar[type[AnthropicParameters]] = AnthropicParameters
    default_secret_env: ClassVar[str | None] = "ANTHROPIC_API_KEY"

    def __init__(
        self,
        parameters: AnthropicParameters,
        client: anthropic.AsyncAnthropic | None,
        *,
        secret_env: str,
    ) -> None:
        self._params = parameters
        # None when the credential is missing: every call then fails with a clear error.
        self._client = client
        self._secret_env = secret_env

    @classmethod
    def from_config(cls, model_config: ModelConfigSnapshot, *, dataset: Dataset) -> Self:
        params = AnthropicParameters.model_validate(model_config.parameters)
        secret_env = model_config.secret_reference or "ANTHROPIC_API_KEY"
        api_key = read_env(secret_env)
        client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=0) if api_key else None
        return cls(params, client, secret_env=secret_env)

    async def generate(
        self,
        *,
        request: ModelRequest,
        model_config: ModelConfigSnapshot,
        timeout_seconds: float,
    ) -> NormalizedModelResponse:
        if self._client is None:
            raise ProviderError(
                ProviderErrorCategory.AUTHENTICATION_FAILED,
                f"Anthropic API key is not configured: set {self._secret_env}",
            )
        body: dict[str, Any] = {
            "model": model_config.model_id,
            "max_tokens": self._params.max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": render_prompt(request.input_data, self._params.prompt_template),
                }
            ],
        }
        if self._params.system_prompt:
            body["system"] = self._params.system_prompt
        if self._params.effort:
            body["output_config"] = {"effort": self._params.effort}
        if self._params.stop_sequences:
            body["stop_sequences"] = self._params.stop_sequences

        try:
            message = await self._client.messages.create(**body, timeout=timeout_seconds)
        except anthropic.APIError as exc:
            raise _translate(exc) from None

        text = "".join(block.text for block in message.content if block.type == "text")
        metadata: dict[str, Any] = {"message_id": message.id, "served_model": message.model}
        details = message.usage.output_tokens_details
        if details is not None and details.thinking_tokens is not None:
            metadata["thinking_tokens"] = details.thinking_tokens
        if message.stop_reason == "refusal" and message.stop_details is not None:
            metadata["refusal_category"] = message.stop_details.category
        return NormalizedModelResponse(
            output_text=text,
            provider=self.provider_name,
            model_id=model_config.model_id,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
            provider_request_id=message._request_id or message.id,
            finish_reason=message.stop_reason,
            raw_metadata=metadata,
        )

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.close()


def _translate(exc: anthropic.APIError) -> ProviderError:
    # APITimeoutError subclasses APIConnectionError, so it is checked first.
    if isinstance(exc, anthropic.APITimeoutError):
        return ProviderError(ProviderErrorCategory.TIMEOUT, "request to Anthropic timed out")
    if isinstance(exc, anthropic.APIConnectionError):
        return ProviderError(
            ProviderErrorCategory.PROVIDER_UNAVAILABLE, "could not connect to Anthropic"
        )
    if isinstance(exc, anthropic.APIStatusError):
        error_type = _error_type(exc.body)
        return ProviderError(
            category_for_status(exc.status_code),
            f"Anthropic returned HTTP {exc.status_code}"
            + (f" ({error_type})" if error_type else ""),
            retry_after_seconds=parse_retry_after(exc.response.headers.get("retry-after")),
        )
    return ProviderError(ProviderErrorCategory.UNKNOWN, type(exc).__name__)


def _error_type(body: object) -> str | None:
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict) and isinstance(error.get("type"), str):
            return str(error["type"])
    return None
