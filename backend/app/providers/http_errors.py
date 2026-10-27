"""Map HTTP failures onto stable provider error categories."""

from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from app.domain.models import ProviderErrorCategory

# Upper bound on a server-requested wait, so one header cannot stall a run.
MAX_RETRY_AFTER_SECONDS = 60.0


def category_for_status(status_code: int) -> ProviderErrorCategory:
    if status_code in (401, 403):
        return ProviderErrorCategory.AUTHENTICATION_FAILED
    if status_code == 429:
        return ProviderErrorCategory.RATE_LIMITED
    if status_code in (408, 504):
        return ProviderErrorCategory.TIMEOUT
    if status_code == 409 or status_code >= 500:
        # 409 is a transient conflict on some providers; 5xx includes 529 "overloaded".
        return ProviderErrorCategory.PROVIDER_UNAVAILABLE
    if status_code in (400, 404, 413, 422):
        return ProviderErrorCategory.INVALID_REQUEST
    return ProviderErrorCategory.UNKNOWN


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Parse a Retry-After header (delta-seconds or HTTP date), capped and never negative."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    return min(max(seconds, 0.0), MAX_RETRY_AFTER_SECONDS)
