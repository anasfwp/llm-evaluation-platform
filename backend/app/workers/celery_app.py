"""Celery application for background evaluation runs.

Start a worker with ``celery -A app.workers.celery_app worker --loglevel INFO``.
Runs are claimed atomically (``queued`` -> ``running``), so a duplicate task
delivery is a no-op. If a worker dies mid-run, the run stays ``running`` with
its partial results; see docs/api.md for stuck-run handling.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings, load_local_env
from app.core.logging import configure_logging

load_local_env()
_settings = get_settings()
configure_logging(_settings.log_level)

celery_app = Celery("llm_eval", broker=_settings.redis_url, include=["app.workers.tasks"])
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    task_ignore_result=True,
    # One run at a time per worker process: a run already bounds its own concurrency.
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
)
