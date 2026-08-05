"""Timezone helpers.

SQLite has no native timestamp type, so SQLAlchemy returns **naive** datetimes
from it even for `DateTime(timezone=True)` columns, while PostgreSQL returns
aware ones. Comparing the two kinds raises `TypeError`, which would surface as a
500 in development and never in production (or vice versa). Every datetime read
back from the database passes through :func:`as_utc` before comparison or
arithmetic.
"""

from __future__ import annotations

from datetime import UTC, datetime


def as_utc(value: datetime) -> datetime:
    """Return `value` as a UTC-aware datetime, assuming naive values are UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def utcnow() -> datetime:
    """Current time as a UTC-aware datetime."""
    return datetime.now(UTC)
