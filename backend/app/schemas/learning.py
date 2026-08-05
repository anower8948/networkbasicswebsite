"""Enrolment, lesson progress, and quiz schemas.

Quiz payloads come in two flavours deliberately kept apart:

* :class:`QuizForAttempt` is what a learner is allowed to see — questions and
  options with **no** correctness flags and no answer key.
* :class:`QuizResult` is returned only after submission and carries the
  correct answers and explanations.

Keeping them as separate types makes it a compile-time-ish mistake to leak an
answer key into the pre-submission payload, rather than something to remember.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import Field

from app.models.enums import AttemptStatus, EnrollmentStatus, ProgressStatus, QuestionType
from app.schemas.catalog import CourseSummary
from app.schemas.common import APIModel
from app.schemas.gamification import AchievementRead


# --------------------------------------------------------------------------- #
# Enrolment and lesson progress
# --------------------------------------------------------------------------- #
class EnrollmentRead(APIModel):
    """An enrolment on its own.

    Deliberately carries no `course` relationship: under `from_attributes`
    Pydantic reads every declared field off the ORM object, and an unloaded
    relationship would trigger a lazy load in async context — which raises
    `MissingGreenlet` rather than quietly issuing a query. Endpoints that want
    the course use :class:`EnrollmentWithCourse` and load it explicitly.
    """

    id: uuid.UUID
    course_id: uuid.UUID
    status: EnrollmentStatus
    progress_percent: float
    last_lesson_id: uuid.UUID | None
    started_at: datetime | None
    completed_at: datetime | None


class EnrollmentWithCourse(EnrollmentRead):
    """An enrolment plus its course, for the "my courses" list."""

    course: CourseSummary


class LessonProgressRead(APIModel):
    lesson_id: uuid.UUID
    status: ProgressStatus
    last_block_index: int
    time_spent_seconds: int
    completed_at: datetime | None


class LessonProgressUpdate(APIModel):
    """Autosaved reading position.

    `time_spent_seconds` is capped for the same reason as the activity ping:
    it is client-supplied and feeds study totals.
    """

    last_block_index: int = Field(default=0, ge=0, le=500)
    time_spent_seconds: int = Field(default=0, ge=0, le=3600)


class LessonCompletionResult(APIModel):
    """What changed when a lesson was marked complete."""

    lesson_id: uuid.UUID
    status: ProgressStatus
    xp_awarded: int
    total_xp: int
    level: int
    leveled_up: bool
    course_progress_percent: float
    course_completed: bool
    next_lesson_id: uuid.UUID | None
    # Badges this completion unlocked, so the UI can celebrate them at the
    # moment they were earned rather than on a later visit to the trophy case.
    new_achievements: list[AchievementRead] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Quizzes — pre-submission
# --------------------------------------------------------------------------- #
class QuizOptionForAttempt(APIModel):
    """An option as the learner sees it. `is_correct` is deliberately absent."""

    id: uuid.UUID
    text: str
    order_index: int


class QuizQuestionForAttempt(APIModel):
    id: uuid.UUID
    prompt: str
    question_type: QuestionType
    media_url: str | None
    points: int
    order_index: int
    options: list[QuizOptionForAttempt] = []
    # For matching questions: the right-hand values to pair against, shuffled.
    match_targets: list[str] = []


class QuizForAttempt(APIModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    title: str
    instructions: str | None
    passing_score: int
    time_limit_seconds: int | None
    questions: list[QuizQuestionForAttempt]

    attempt_id: uuid.UUID
    attempt_number: int
    attempts_remaining: int | None = None


# --------------------------------------------------------------------------- #
# Quizzes — submission and result
# --------------------------------------------------------------------------- #
class QuizAnswer(APIModel):
    """One learner response.

    The shape depends on the question type:

    * single/true-false — `option_ids` with one entry
    * multiple choice   — `option_ids` with zero or more
    * fill-blank / subnet-calc / CLI — `text`
    * ordering          — `values`, the option ids in the chosen order
    * matching          — `pairs`, {left option id: chosen right-hand value}
    """

    question_id: uuid.UUID
    option_ids: list[uuid.UUID] = []
    text: str | None = Field(default=None, max_length=500)
    values: list[str] = []
    pairs: dict[str, str] = {}


class QuizSubmission(APIModel):
    answers: list[QuizAnswer] = Field(min_length=1, max_length=200)


class QuestionResult(APIModel):
    """Per-question feedback, returned only after submission."""

    question_id: uuid.UUID
    is_correct: bool
    points_earned: int
    points_possible: int
    explanation: str | None
    correct_option_ids: list[uuid.UUID] = []
    correct_text: str | None = None
    correct_order: list[str] = []
    correct_pairs: dict[str, str] = {}


class QuizResult(APIModel):
    attempt_id: uuid.UUID
    quiz_id: uuid.UUID
    lesson_id: uuid.UUID
    status: AttemptStatus
    passed: bool
    score_percent: float
    points_earned: int
    points_possible: int
    passing_score: int
    attempt_number: int
    attempts_remaining: int | None
    results: list[QuestionResult]

    xp_awarded: int = 0
    total_xp: int = 0
    level: int = 1
    leveled_up: bool = False
    new_achievements: list[AchievementRead] = Field(default_factory=list)


class QuizAttemptSummary(APIModel):
    """A past attempt, for the lesson's attempt history."""

    id: uuid.UUID
    attempt_number: int
    status: AttemptStatus
    score_percent: float | None
    points_earned: int
    points_possible: int
    submitted_at: datetime | None


class AnswerKeyPayload(APIModel):
    """Shape of `quiz_questions.answer_key` for non-option question types."""

    text: str | None = None
    accepted: list[str] = []
    case_sensitive: bool = False
    order: list[str] = []
    pairs: dict[str, str] = {}
    extra: dict[str, Any] = {}
