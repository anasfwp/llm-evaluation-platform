from __future__ import annotations

from app.providers.base import BaseProvider
from app.providers.fake import FakeProvider

# Hosted and OpenAI-compatible adapters are added in Phase 3.
PROVIDERS: dict[str, type[BaseProvider]] = {
    FakeProvider.provider_name: FakeProvider,
}


def get_provider(name: str) -> type[BaseProvider]:
    try:
        return PROVIDERS[name]
    except KeyError:
        supported = ", ".join(sorted(PROVIDERS))
        raise KeyError(f"unknown provider '{name}' (supported: {supported})") from None
