"""Best-effort redaction of credential-like values before text is stored or printed.

This is a safety net, not a guarantee: adapters must still avoid putting
secrets into error messages in the first place.
"""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # Authorization: Bearer <token> / Basic <token>
    re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}"),
    # key=value or "key": "value" for credential-like key names
    re.compile(
        r"(?i)(\b[\w-]*(?:api[_-]?key|secret|token|password|authorization)[\w-]*\b"
        r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}]+)"
    ),
    # Common provider key shapes, e.g. sk-..., sk-ant-..., AIza...
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
)


def redact_secrets(text: str) -> str:
    redacted = _PATTERNS[0].sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    redacted = _PATTERNS[1].sub(lambda m: f"{m.group(1)}{REDACTED}", redacted)
    for pattern in _PATTERNS[2:]:
        redacted = pattern.sub(REDACTED, redacted)
    return redacted


def safe_error_message(text: str, max_length: int = 500) -> str:
    """Redact and truncate an error message for storage in results/logs."""
    message = redact_secrets(text.strip())
    if len(message) > max_length:
        message = message[: max_length - 3] + "..."
    return message
