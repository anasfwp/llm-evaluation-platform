"""How a queued run reaches execution: Celery/Redis in normal operation, inline for tests."""

from __future__ import annotations

import uuid
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings


class RunDispatcher(Protocol):
    def dispatch(self, run_id: uuid.UUID) -> None: ...


class CeleryDispatcher:
    def dispatch(self, run_id: uuid.UUID) -> None:
        from app.workers.tasks import execute_run_task

        execute_run_task.delay(str(run_id))


class InlineDispatcher:
    """Executes the run synchronously in the calling process. Tests and local experiments only."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def dispatch(self, run_id: uuid.UUID) -> None:
        from app.services.run_service import execute_run

        execute_run(self._session_factory, run_id)


def build_dispatcher(settings: Settings, session_factory: sessionmaker[Session]) -> RunDispatcher:
    if settings.run_dispatcher == "inline":
        return InlineDispatcher(session_factory)
    return CeleryDispatcher()
