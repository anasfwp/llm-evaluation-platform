"""Structured JSON logging with request/run/case correlation IDs.

Request and run IDs and case keys live in context variables so every log line
emitted while handling a request, executing a run, or evaluating a case carries
them automatically. Messages are
passed through secret redaction; prompt and completion text is never logged.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

from app.utils.redaction import redact_secrets

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
run_id_var: ContextVar[str | None] = ContextVar("run_id", default=None)
case_key_var: ContextVar[str | None] = ContextVar("case_key", default=None)

_STANDARD_ATTRS = set(vars(logging.makeLogRecord({}))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        if (request_id := request_id_var.get()) is not None:
            payload["request_id"] = request_id
        if (run_id := run_id_var.get()) is not None:
            payload["run_id"] = run_id
        if (case_key := case_key_var.get()) is not None:
            payload["case_key"] = case_key
        for key, value in vars(record).items():
            if key not in _STANDARD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str) -> None:
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(level)
