"""FastAPI application factory.

Wires middleware, exception handlers, and the versioned router. Import-time
side effects are kept to a minimum so tests can build an isolated app instance.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import configure_logging, get_logger
from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.db.session import dispose_engine

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Start-up and shut-down hooks."""
    configure_logging()
    logger.info("Starting %s", settings.APP_NAME, extra={"environment": settings.ENVIRONMENT})
    yield
    await dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Build and configure the ASGI application."""
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description=(
            "Backend for the Network Learning Platform — interactive networking "
            "education from foundations through CCNA and beyond."
        ),
        lifespan=lifespan,
        # Interactive docs are useful in every environment except production,
        # where they expose the full attack surface to unauthenticated callers.
        docs_url=None if settings.ENVIRONMENT == "production" else "/docs",
        redoc_url=None if settings.ENVIRONMENT == "production" else "/redoc",
        openapi_url=None if settings.ENVIRONMENT == "production" else "/openapi.json",
    )

    _register_middleware(app)
    _register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)
    return app


# --------------------------------------------------------------------------- #
# Middleware
# --------------------------------------------------------------------------- #
def _register_middleware(app: FastAPI) -> None:
    """Install middleware.

    Order matters and is the reverse of registration: the last one added runs
    outermost. So the body limit is registered last and rejects an over-sized
    payload before anything else touches it, and the request logger is
    registered first so it wraps the handler and nothing else.
    """
    # Innermost: sees the final response, so it can decide whether an endpoint
    # already set its own Cache-Control.
    app.add_middleware(SecurityHeadersMiddleware)

    app.add_middleware(GZipMiddleware, minimum_size=settings.GZIP_MIN_BYTES)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        # Required for the refresh-token cookie to be sent cross-origin during
        # local development (Vite on :5173, API on :8000).
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
        max_age=600,
    )

    # A spoofed Host header poisons the absolute URLs in password-reset mail,
    # so it is rejected before any handler can read it. `*` is the default and
    # is correct behind a proxy that has already matched the host.
    if settings.ALLOWED_HOSTS != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)

    # Outermost: rejects on Content-Length before the body is buffered.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.MAX_REQUEST_BYTES)

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[object]]
    ) -> object:
        """Tag every request with an ID and time it."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = (time.perf_counter() - started) * 1000
        response.headers[REQUEST_ID_HEADER] = request_id  # type: ignore[attr-defined]
        response.headers["X-Response-Time-ms"] = f"{duration_ms:.2f}"  # type: ignore[attr-defined]

        logger.info(
            "%s %s %s",
            request.method,
            request.url.path,
            getattr(response, "status_code", "?"),
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": getattr(response, "status_code", None),
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response


# --------------------------------------------------------------------------- #
# Exception handlers
# --------------------------------------------------------------------------- #
def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        """Domain errors carry their own status code and stable error code."""
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Reshape FastAPI's validation errors into the standard envelope."""
        fields: dict[str, str] = {}
        for error in exc.errors():
            # Drop the leading "body"/"query" segment for a client-friendly path.
            location = ".".join(str(part) for part in error["loc"][1:]) or "request"
            fields[location] = error["msg"]

        return JSONResponse(
            # Literal rather than `status.HTTP_422_*`: Starlette renamed the
            # constant and the old name now emits a deprecation warning.
            status_code=422,
            content={
                "error": {
                    "code": "validation_error",
                    "message": "The submitted data is invalid.",
                    "details": {"fields": fields},
                }
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        """Keep 404s and other framework errors in the same envelope."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": f"http_{exc.status_code}",
                    "message": str(exc.detail),
                }
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        """Last resort: log the traceback, return an opaque 500.

        Internal details never reach the client — they would leak schema and
        file paths to an attacker.
        """
        request_id = getattr(request.state, "request_id", None)
        logger.exception(
            "Unhandled exception", extra={"request_id": request_id, "path": request.url.path}
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "internal_server_error",
                    "message": "An unexpected error occurred.",
                    "details": {"request_id": request_id} if request_id else {},
                }
            },
        )


app = create_app()
