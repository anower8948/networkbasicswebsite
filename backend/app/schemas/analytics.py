"""Instructor and admin analytics.

Every figure here is **aggregate**. Instructor tooling on a learning platform
slides easily into surveillance, so the line drawn is: an instructor may see how
the *content* is performing, and may see a roster of who is enrolled and how far
they have got, but not a per-learner activity trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from app.schemas.common import APIModel


class PlatformOverview(APIModel):
    """The numbers on the admin dashboard.

    The two windowed counts are named `..._week` rather than `..._7d`: the
    camelCase alias generator capitalises each underscore-separated segment, so
    `active_users_7d` serialises as `activeUsers7D` — a capital D that no
    client author would guess and no type-checker would catch, because the
    TypeScript interface is hand-written against the wire format.
    """

    total_users: int
    active_users_week: int
    new_users_week: int
    total_enrollments: int
    lessons_completed: int
    labs_completed: int
    quizzes_taken: int
    certificates_issued: int


class CoursePerformance(APIModel):
    """How one course is doing, across everyone taking it."""

    course_id: uuid.UUID
    slug: str
    title: str
    enrollments: int
    completions: int
    completion_rate: float
    average_progress: float


class LabPerformance(APIModel):
    """Where a lab is too hard — or too easy.

    `average_hints` is the most useful column: an objective nobody can do
    without a hint is an objective that is badly worded, not a cohort that is
    weak.
    """

    lab_id: uuid.UUID
    slug: str
    title: str
    attempts: int
    passes: int
    pass_rate: float
    average_score: float
    average_hints: float


class QuizQuestionStat(APIModel):
    """A question everyone gets wrong is usually a bad question."""

    quiz_id: uuid.UUID
    quiz_title: str
    attempts: int
    average_score: float
    pass_rate: float


class RosterEntry(APIModel):
    """One learner's standing, for an instructor's class list."""

    user_id: uuid.UUID
    display_name: str
    email: str
    level: int
    total_xp: int
    lessons_completed: int
    labs_completed: int
    last_active_at: datetime | None


class AnalyticsReport(APIModel):
    overview: PlatformOverview
    courses: list[CoursePerformance]
    labs: list[LabPerformance]
    quizzes: list[QuizQuestionStat]
