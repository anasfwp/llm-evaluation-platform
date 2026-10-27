"""Credential lookup. Values come from the process environment and are never persisted."""

from __future__ import annotations

import os

from app.domain.models import ProviderErrorCategory
from app.providers.base import ProviderError


def read_env(name: str | None) -> str | None:
    """Return the variable's value, treating unset and empty the same way."""
    if not name:
        return None
    return os.environ.get(name) or None


def require_env(name: str | None, *, purpose: str) -> str:
    """Return the variable's value or raise a non-retryable ``ProviderError``.

    The message names the variable but never includes a value.
    """
    value = read_env(name)
    if value is None:
        raise ProviderError(
            ProviderErrorCategory.AUTHENTICATION_FAILED,
            f"{purpose} is not configured: set the environment variable {name or '(none)'}",
        )
    return value
