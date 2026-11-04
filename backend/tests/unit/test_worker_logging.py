from __future__ import annotations

import logging

from celery.signals import setup_logging

from app.core.logging import JsonFormatter
from app.workers import celery_app  # noqa: F401  (connects the signal receiver)


def test_worker_startup_keeps_json_logging() -> None:
    # Celery clears the root logger's handlers at startup unless a receiver answers this signal.
    receivers = setup_logging.send(
        sender=None, loglevel=logging.INFO, logfile=None, format="", colorize=False
    )

    assert receivers
    assert any(isinstance(h.formatter, JsonFormatter) for h in logging.getLogger().handlers)
