from __future__ import annotations

import logging

import redis
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.deps import SessionDep, SettingsDep

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health/live")
def live() -> dict[str, str]:
    """The process is up and serving requests."""
    return {"status": "ok"}


@router.get("/health/ready", responses={503: {"description": "A dependency is unavailable"}})
def ready(session: SessionDep, settings: SettingsDep) -> JSONResponse:
    """Critical dependencies (database, and the queue when Celery dispatch is used) respond."""
    checks: dict[str, str] = {}
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        logger.warning("readiness: database unavailable", exc_info=True)
        checks["database"] = "unavailable"
    if settings.run_dispatcher == "celery":
        try:
            client = redis.Redis.from_url(
                settings.redis_url, socket_connect_timeout=1, socket_timeout=1
            )
            client.ping()
            checks["queue"] = "ok"
        except Exception:
            logger.warning("readiness: queue unavailable", exc_info=True)
            checks["queue"] = "unavailable"
    healthy = all(value == "ok" for value in checks.values())
    return JSONResponse(
        status_code=200 if healthy else 503,
        content={"status": "ready" if healthy else "not_ready", "checks": checks},
    )
