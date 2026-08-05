"""Cross-cutting HTTP middleware: security headers and payload limits.

Two things live here that the application factory used to do inline, plus two
that Part 10 adds.

**Security headers are defence in depth, not the defence.** The API returns
JSON, so a Content-Security-Policy on it can be maximally strict — there is
nothing legitimate to load. The policy that actually protects the *application*
is the one nginx sends with `index.html`; this one exists so that a browser
which is somehow persuaded to render an API response cannot be made to do
anything with it.

**The body limit is enforced before the body is read.** Checking `Content-Length`
in a handler is too late — Starlette has already buffered the payload by then.
This rejects on the header, and also guards the streaming case where a client
omits `Content-Length` entirely.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from app.core.config import settings

# An API that returns nothing but JSON should be permitted to load nothing at
# all. `frame-ancestors 'none'` is the modern X-Frame-Options and is honoured
# where the old header is not (nested browsing contexts).
API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"

# Features this application never uses. Denying them means an injected script
# cannot silently reach for a camera or a location.
PERMISSIONS_POLICY = (
    "accelerometer=(), autoplay=(), camera=(), display-capture=(), "
    "encrypted-media=(), fullscreen=(self), geolocation=(), gyroscope=(), "
    "magnetometer=(), microphone=(), midi=(), payment=(), usb=()"
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to every response."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        headers = response.headers

        headers["X-Content-Type-Options"] = "nosniff"
        headers["X-Frame-Options"] = "DENY"
        headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        headers["Content-Security-Policy"] = API_CSP
        headers["Permissions-Policy"] = PERMISSIONS_POLICY
        # Isolates this origin's browsing context group from any window that
        # opened it, which is what closes cross-origin `window.opener` attacks.
        headers["Cross-Origin-Opener-Policy"] = "same-origin"
        headers["Cross-Origin-Resource-Policy"] = "same-origin"

        # Only over TLS: sending this from a plain-HTTP dev server would pin
        # localhost to HTTPS in the developer's browser, and there is no way to
        # un-pin it except by clearing site data.
        if settings.HSTS_ENABLED:
            headers["Strict-Transport-Security"] = (
                f"max-age={settings.HSTS_MAX_AGE_SECONDS}; includeSubDomains"
            )

        # Authenticated JSON must never be stored by a shared cache. Endpoints
        # that *are* cacheable set their own Cache-Control and are left alone.
        if "cache-control" not in headers:
            headers["Cache-Control"] = "no-store"

        return response


class BodySizeLimitMiddleware:
    """Reject over-sized payloads before they are buffered into memory.

    Implemented against the raw ASGI interface rather than `BaseHTTPMiddleware`
    because the latter only sees the request once the body is already read —
    which is precisely the cost this exists to avoid.
    """

    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = self._content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._too_large(scope, receive, send)
            return

        # A client can omit Content-Length and stream the body, so the running
        # total is checked as chunks arrive too.
        received = 0
        limit = self.max_bytes
        exceeded = False

        async def counting_receive() -> dict:
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    # Truncate rather than pass the oversized body downstream.
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, counting_receive, send)

    @staticmethod
    def _content_length(scope: dict) -> int | None:
        for key, value in scope.get("headers", []):
            if key == b"content-length":
                try:
                    return int(value)
                except ValueError:
                    return None
        return None

    async def _too_large(self, scope: dict, receive: Callable, send: Callable) -> None:
        response = JSONResponse(
            status_code=413,
            content={
                "error": {
                    "code": "payload_too_large",
                    "message": (
                        f"Request body exceeds the {self.max_bytes // (1024 * 1024)} MB limit."
                    ),
                }
            },
        )
        await response(scope, receive, send)
