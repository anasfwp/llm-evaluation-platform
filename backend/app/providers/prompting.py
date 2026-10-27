"""Turn a case's structured input into the prompt text sent to a chat model.

Templates use ``{{field}}`` placeholders that are replaced with input values.
Only plain substitution is supported (no attribute access or expressions), so
a template supplied through the API cannot execute anything.
"""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ProviderErrorCategory
from app.providers.base import ProviderError

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
# Input keys tried, in order, when no template is configured.
_PROMPT_KEYS = ("prompt", "question", "input", "query")


class PromptParameters(BaseModel):
    """Prompt settings shared by chat providers."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_prompt: str | None = Field(default=None, max_length=20_000)
    prompt_template: str | None = Field(default=None, min_length=1, max_length=20_000)


def render_prompt(input_data: dict[str, Any], template: str | None) -> str:
    """Render the user prompt for one case.

    Without a template, the first of ``prompt``/``question``/``input``/``query``
    that holds a string is used, then a sole string value; anything else is sent
    as canonical JSON so structured inputs are never silently dropped.
    """
    if template is not None:
        referenced = {match.group(1) for match in _PLACEHOLDER.finditer(template)}
        missing = sorted(referenced - set(input_data))
        if missing:
            raise ProviderError(
                ProviderErrorCategory.INVALID_REQUEST,
                f"prompt_template references missing input fields: {', '.join(missing)}",
            )
        return _PLACEHOLDER.sub(lambda match: _as_text(input_data[match.group(1)]), template)

    for key in _PROMPT_KEYS:
        value = input_data.get(key)
        if isinstance(value, str):
            return value
    values = list(input_data.values())
    if len(values) == 1 and isinstance(values[0], str):
        return values[0]
    return json.dumps(input_data, ensure_ascii=False, sort_keys=True)


def _as_text(value: Any) -> str:
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
