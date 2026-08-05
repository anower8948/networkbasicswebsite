"""In-process rate limiting for credential and email-sending endpoints.

Scope and limitations
---------------------
This is a **single-process, in-memory** limiter. It resets on restart and each
worker keeps its own counters, so N uvicorn workers permit N times the
configured rate. That is an acceptable trade for the endpoints it guards — it
turns an unbounded password-reset mail flood into a bounded one — but it is not
a substitute for a shared limiter.

Part 10 replaces the backing store with Redis, at which point the limits become
global. The :class:`RateLimiter` interface is deliberately narrow so that swap
touches only this file.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import RateLimitExceeded


@dataclass(frozen=True, slots=True)
class RateLimitRule:
    """Allow at most `limit` events per `window_seconds` for a given key."""

    limit: int
    window_seconds: int


class RateLimiter:
    """Sliding-window counter keyed by an arbitrary string."""

    def __init__(self) -> None:
        # key -> timestamps of recent hits, oldest first.
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, rule: RateLimitRule) -> None:
        """Record a hit, raising :class:`RateLimitExceeded` if over the limit."""
        if not settings.RATE_LIMIT_ENABLED:
            return

        now = time.monotonic()
        cutoff = now - rule.window_seconds
        hits = self._hits[key]

        # Drop timestamps that have aged out of the window.
        while hits and hits[0] < cutoff:
            hits.popleft()

        if len(hits) >= rule.limit:
            retry_after = int(hits[0] + rule.window_seconds - now) + 1
            raise RateLimitExceeded(
                "Too many attempts. Please try again later.",
                details={"retryAfterSeconds": max(retry_after, 1)},
            )

        hits.append(now)

    def reset(self, key: str | None = None) -> None:
        """Clear one key, or everything. Used by tests."""
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)

    def prune(self, max_window_seconds: int = 3600) -> int:
        """Drop keys with no recent activity, bounding memory growth."""
        cutoff = time.monotonic() - max_window_seconds
        stale = [key for key, hits in self._hits.items() if not hits or hits[-1] < cutoff]
        for key in stale:
            del self._hits[key]
        return len(stale)


limiter = RateLimiter()


def email_rule() -> RateLimitRule:
    """Limit for anything that sends mail to a user-supplied address."""
    return RateLimitRule(limit=settings.RATE_LIMIT_EMAIL_PER_HOUR, window_seconds=3600)


def login_rule() -> RateLimitRule:
    """Limit for credential submission, to slow online password guessing."""
    return RateLimitRule(limit=settings.RATE_LIMIT_LOGIN_PER_15_MIN, window_seconds=900)
