from __future__ import annotations

import uuid

from app.db.session import get_session_factory
from app.services.run_service import execute_run
from app.workers.celery_app import celery_app


@celery_app.task(name="runs.execute")  # type: ignore[untyped-decorator]
def execute_run_task(run_id: str) -> None:
    # No Celery-level retries: the engine already retries transient provider errors per case,
    # and re-running a whole evaluation could double provider spend.
    execute_run(get_session_factory(), uuid.UUID(run_id))
