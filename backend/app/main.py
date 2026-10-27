"""FastAPI application factory.

Run locally with ``uvicorn app.main:create_app --factory``. This API has no
authentication yet: keep it bound to localhost and never expose it publicly,
because it can trigger provider calls that cost money.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.core.config import Settings, get_settings, load_local_env
from app.core.errors import (
    ConflictError,
    DependencyUnavailableError,
    InvalidRequestError,
    Issue,
    NotFoundError,
    ServiceError,
    format_location,
)
from app.core.logging import configure_logging, request_id_var
from app.db.session import build_engine, build_session_factory
from app.services.dispatch import build_dispatcher

logger = logging.getLogger("app.api")

_STATUS_BY_ERROR: dict[type[ServiceError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    InvalidRequestError: 422,
    DependencyUnavailableError: 503,
}
_CODE_BY_STATUS = {
    400: "BAD_REQUEST",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    413: "PAYLOAD_TOO_LARGE",
    500: "INTERNAL_ERROR",
}


def _error(
    status_code: int, code: str, message: str, details: list[Issue] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": [
                    {"field": issue.location or None, "message": issue.message}
                    for issue in details or []
                ],
                "request_id": request_id_var.get(),
            }
        },
    )


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error(_: Request, exc: ServiceError) -> JSONResponse:
        status_code = _STATUS_BY_ERROR.get(type(exc), 400)
        return _error(status_code, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            Issue(location=format_location(err.get("loc", ())), message=err.get("msg", "invalid"))
            for err in exc.errors()
        ]
        return _error(422, "VALIDATION_ERROR", "The request is invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODE_BY_STATUS.get(exc.status_code, "HTTP_ERROR")
        return _error(exc.status_code, code, str(exc.detail))


def _request_context(
    settings: Settings,
) -> Callable[[Request, Callable[[Request], Awaitable[Response]]], Awaitable[Response]]:
    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("X-Request-ID", "")
        request_id = incoming if 0 < len(incoming) <= 64 else f"req_{uuid.uuid4().hex}"
        token = request_id_var.set(request_id)
        start = time.perf_counter()
        try:
            declared = request.headers.get("Content-Length")
            if (
                declared is not None
                and declared.isdigit()
                and int(declared) > settings.max_request_bytes
            ):
                response: Response = _error(
                    413, "PAYLOAD_TOO_LARGE", "The request body is too large."
                )
                return response
            try:
                response = await call_next(request)
            except Exception:
                logger.exception("unhandled error")
                response = _error(500, "INTERNAL_ERROR", "An unexpected error occurred.")
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )
            return response
        finally:
            request_id_var.reset(token)

    return middleware


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:  # real server start; tests pass explicit settings
        load_local_env()
        settings = get_settings()
    configure_logging(settings.log_level)
    session_factory = build_session_factory(build_engine(settings.database_url))

    app = FastAPI(
        title="LLM Evaluation and Monitoring Platform",
        version=__version__,
        description="Evaluate LLM and RAG applications: datasets, runs, results, and reports.",
    )
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.dispatcher = build_dispatcher(settings, session_factory)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.middleware("http")(_request_context(settings))
    _register_error_handlers(app)

    app.include_router(health.router)
    app.include_router(api_router, prefix="/api/v1")
    return app
