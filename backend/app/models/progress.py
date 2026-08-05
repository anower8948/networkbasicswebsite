"""Per-learner progress: enrollments, lesson progress, quiz attempts, notes."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONColumn, enum_column
from app.models.enums import AttemptStatus, EnrollmentStatus, ProgressStatus

if TYPE_CHECKING:
    from app.models.catalog import Course, Lesson, Quiz
    from app.models.user import User


class Enrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A learner's registration in a course."""

    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollments_user_id_course_id"),
        Index("ix_enrollments_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        enum_column(EnrollmentStatus, length=20),
        default=EnrollmentStatus.ACTIVE,
        nullable=False,
    )
    # Cached completion percentage (0–100); recomputed when a lesson completes.
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("lessons.id", ondelete="SET NULL")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="enrollments")
    course: Mapped[Course] = relationship(back_populates="enrollments")


class LessonProgress(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tracks one learner's state within one lesson."""

    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_lesson_progress_user_id_lesson_id"),
        Index("ix_lesson_progress_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[ProgressStatus] = mapped_column(
        enum_column(ProgressStatus, length=20),
        default=ProgressStatus.NOT_STARTED,
        nullable=False,
    )
    # Index of the furthest content block reached, so the reader can resume.
    last_block_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="lesson_progress")
    lesson: Mapped[Lesson] = relationship(back_populates="progress_records")


class QuizAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One submission of a quiz.

    `responses` stores the learner's raw answers so a quiz can be reviewed, and
    re-graded if a question's answer key is later corrected.
    """

    __tablename__ = "quiz_attempts"
    __table_args__ = (Index("ix_quiz_attempts_user_quiz", "user_id", "quiz_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    quiz_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[AttemptStatus] = mapped_column(
        enum_column(AttemptStatus, length=20),
        default=AttemptStatus.IN_PROGRESS,
        nullable=False,
    )
    score_percent: Mapped[float | None] = mapped_column(Float)
    points_earned: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points_possible: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    responses: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship()
    quiz: Mapped[Quiz] = relationship(back_populates="attempts")


class Note(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A learner's private note on a lesson."""

    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_user_lesson", "user_id", "lesson_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # Anchors the note to a content block so it renders beside the right passage.
    block_index: Mapped[int | None] = mapped_column(Integer)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    user: Mapped[User] = relationship(back_populates="notes")
    lesson: Mapped[Lesson] = relationship(back_populates="notes")


class Bookmark(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved lesson for quick return."""

    __tablename__ = "bookmarks"
    __table_args__ = (
        UniqueConstraint("user_id", "lesson_id", name="uq_bookmarks_user_id_lesson_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lesson_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label: Mapped[str | None] = mapped_column(String(120))

    user: Mapped[User] = relationship(back_populates="bookmarks")
    lesson: Mapped[Lesson] = relationship(back_populates="bookmarks")
