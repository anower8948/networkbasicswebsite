"""Achievements, leaderboards, and certificates.

Achievement criteria are **declarative**, like lab grading rules: an achievement
is a row of data, not a function. That means new badges can be seeded or
authored by an instructor without a deployment, and — more usefully — that every
badge is evaluated against one shared metric snapshot rather than each running
its own queries.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AchievementCategory
from app.schemas.common import APIModel

# Everything an achievement may test. Deliberately a closed set: an unknown
# metric is an authoring error, and this is where it is caught.
Metric = Literal[
    "total_xp",
    "level",
    "lessons_completed",
    "courses_completed",
    "labs_completed",
    "quizzes_passed",
    "current_streak_days",
    "longest_streak_days",
    "perfect_labs",
    "topologies_saved",
    "study_minutes",
]

Operator = Literal[">=", ">", "==", "<=", "<"]


class CriteriaModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MetricCriterion(CriteriaModel):
    """One threshold on one metric — the shape most badges need."""

    metric: Metric
    operator: Operator = ">="
    value: int = Field(ge=0, le=1_000_000)


class AllOfCriteria(CriteriaModel):
    """Every listed criterion must hold.

    There is no `any_of`: a badge earned by either of two unrelated things is
    two badges, and splitting them tells the learner more.
    """

    all_of: list[MetricCriterion] = Field(min_length=1, max_length=8, alias="allOf")


AchievementCriteria = MetricCriterion | AllOfCriteria


class AchievementRead(APIModel):
    """A badge as the learner sees it."""

    id: uuid.UUID
    slug: str
    title: str
    description: str
    icon: str | None
    category: AchievementCategory
    xp_reward: int
    earned: bool = False
    earned_at: datetime | None = None
    # Progress toward the badge, 0–100. `None` for a secret badge that has not
    # been earned — showing a progress bar would give away what it wants.
    progress_percent: float | None = None


class AchievementList(APIModel):
    items: list[AchievementRead]
    earned_count: int
    total_count: int


class LeaderboardEntry(APIModel):
    rank: int
    user_id: uuid.UUID
    display_name: str
    avatar_url: str | None
    country_code: str | None
    level: int
    xp: int
    # Set for the signed-in learner's own row, so the UI can highlight it.
    is_you: bool = False


class Leaderboard(APIModel):
    scope: Literal["all_time", "monthly", "weekly"]
    entries: list[LeaderboardEntry]
    # The requester's own standing, even when they are outside the top N —
    # a board that never shows you your own rank is demotivating.
    you: LeaderboardEntry | None = None


class CertificateRead(APIModel):
    id: uuid.UUID
    course_id: uuid.UUID
    course_title: str
    serial: str
    verification_code: str
    recipient_name: str
    final_score: int | None
    issued_at: datetime
    revoked_at: datetime | None

    @property
    def is_valid(self) -> bool:
        return self.revoked_at is None


class CertificateVerification(APIModel):
    """The public answer to "is this certificate real?".

    Carries the holder's display name and the course, and nothing else — a
    verification endpoint that leaked an email address would be a privacy bug,
    and the code is designed to be pasted into a CV.
    """

    valid: bool
    recipient_name: str | None = None
    course_title: str | None = None
    issued_at: datetime | None = None
    revoked: bool = False
