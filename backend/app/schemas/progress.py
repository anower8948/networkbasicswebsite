"""Progress, level, and activity schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.models.enums import XPReason
from app.schemas.common import APIModel


class LevelProgressRead(APIModel):
    """Everything a level progress bar needs, precomputed server-side.

    The level curve is defined in one place (`services.progress_service`); the
    client must not reimplement it, or the two will disagree.
    """

    level: int
    total_xp: int
    current_level_xp: int
    next_level_xp: int
    xp_into_level: int
    xp_for_next_level: int
    percent_to_next_level: float
    is_max_level: bool


class XPTransactionRead(APIModel):
    id: uuid.UUID
    amount: int
    reason: XPReason
    reference_type: str | None
    reference_id: uuid.UUID | None
    created_at: datetime


class ProgressSummary(APIModel):
    """The dashboard payload — one request instead of five."""

    total_xp: int
    level: LevelProgressRead
    lessons_completed: int
    courses_completed: int
    labs_completed: int
    quizzes_passed: int
    total_study_seconds: int
    current_streak_days: int
    longest_streak_days: int
    xp_this_week: int
    last_activity_at: datetime | None
    recent_xp: list[XPTransactionRead]


class ActivityPing(APIModel):
    """Reports study time so streaks advance and time-spent accumulates.

    The client is not trusted with this number. It is capped at one hour per
    ping so a tampered or buggy client cannot inflate study totals — and by
    extension a leaderboard — with a single request. Legitimate clients ping
    every few minutes while a lesson is open.
    """

    study_seconds: int = Field(default=0, ge=0, le=3600)
