from __future__ import annotations

from app.providers.anthropic_messages import AnthropicProvider
from app.providers.base import BaseProvider
from app.providers.fake import FakeProvider
from app.providers.openai_compatible import OpenAICompatibleProvider, OpenAIProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    cls.provider_name: cls
    for cls in (FakeProvider, AnthropicProvider, OpenAIProvider, OpenAICompatibleProvider)
}


def get_provider(name: str) -> type[BaseProvider]:
    try:
        return PROVIDERS[name]
    except KeyError:
        supported = ", ".join(sorted(PROVIDERS))
        raise KeyError(f"unknown provider '{name}' (supported: {supported})") from None
