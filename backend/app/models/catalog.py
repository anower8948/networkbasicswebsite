"""Course catalogue: tracks → courses → modules → lessons, plus quizzes.

The hierarchy is a strict tree. Ordering within each level is an explicit
`order_index` rather than an implicit creation order, so instructors can
reorder content in the admin panel without touching timestamps.

Lesson bodies are stored as structured JSON (a list of typed content blocks)
rather than raw HTML. This keeps the renderer in control of presentation,
allows interactive blocks (simulator embeds, subnet calculators, animated
diagrams) to sit inline with prose, and avoids storing user-authored HTML that
would need sanitising.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
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
from app.models.enums import Difficulty, LessonType, QuestionType, TrackLevel

if TYPE_CHECKING:
    from app.models.gamification import Certificate
    from app.models.lab import Lab
    from app.models.progress import Bookmark, Enrollment, LessonProgress, Note, QuizAttempt


class Track(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A top-level learning path (Foundation / Intermediate / Advanced)."""

    __tablename__ = "tracks"

    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    level: Mapped[TrackLevel] = mapped_column(enum_column(TrackLevel, length=20), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80))
    # Wide enough for a CSS custom-property reference such as
    # `var(--color-track-intermediate)`, which is what the seed data uses and
    # what the design system expects. 20 characters fitted a hex code and
    # nothing else — SQLite ignored the overflow, PostgreSQL rejected it.
    accent_color: Mapped[str | None] = mapped_column(String(64))
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    courses: Mapped[list[Course]] = relationship(
        back_populates="track", cascade="all, delete-orphan", order_by="Course.order_index"
    )


class Course(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A course inside a track, e.g. "IP Addressing & Subnetting"."""

    __tablename__ = "courses"
    __table_args__ = (Index("ix_courses_track_order", "track_id", "order_index"),)

    track_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tracks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[Difficulty] = mapped_column(
        enum_column(Difficulty, length=20),
        default=Difficulty.BEGINNER,
        nullable=False,
    )
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cover_image_url: Mapped[str | None] = mapped_column(String(512))
    # Free-form tags, e.g. ["ccna", "subnetting", "ipv4"].
    tags: Mapped[list[str]] = mapped_column(JSONColumn, default=list, nullable=False)
    # Slugs of courses a learner should finish first; enforced in the service layer.
    prerequisites: Mapped[list[str]] = mapped_column(JSONColumn, default=list, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    grants_certificate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    track: Mapped[Track] = relationship(back_populates="courses")
    modules: Mapped[list[Module]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="Module.order_index"
    )
    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )
    certificates: Mapped[list[Certificate]] = relationship(back_populates="course")


class Module(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A chapter grouping related lessons within a course."""

    __tablename__ = "modules"
    __table_args__ = (
        UniqueConstraint("course_id", "slug", name="uq_modules_course_id_slug"),
        Index("ix_modules_course_order", "course_id", "order_index"),
    )

    course_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    course: Mapped[Course] = relationship(back_populates="modules")
    lessons: Mapped[list[Lesson]] = relationship(
        back_populates="module", cascade="all, delete-orphan", order_by="Lesson.order_index"
    )


class Lesson(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single unit of learning."""

    __tablename__ = "lessons"
    __table_args__ = (
        UniqueConstraint("module_id", "slug", name="uq_lessons_module_id_slug"),
        Index("ix_lessons_module_order", "module_id", "order_index"),
    )

    module_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(500))
    lesson_type: Mapped[LessonType] = mapped_column(
        enum_column(LessonType, length=20),
        default=LessonType.THEORY,
        nullable=False,
    )
    # Ordered list of typed content blocks; see docs/DATABASE.md for the shape.
    content_blocks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )
    # Learning objectives shown before the lesson and used for grading rubrics.
    objectives: Mapped[list[str]] = mapped_column(JSONColumn, default=list, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    module: Mapped[Module] = relationship(back_populates="lessons")
    quiz: Mapped[Quiz | None] = relationship(
        back_populates="lesson", uselist=False, cascade="all, delete-orphan"
    )
    labs: Mapped[list[Lab]] = relationship(back_populates="lesson")
    progress_records: Mapped[list[LessonProgress]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan"
    )
    notes: Mapped[list[Note]] = relationship(back_populates="lesson", cascade="all, delete-orphan")
    bookmarks: Mapped[list[Bookmark]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan"
    )


class Quiz(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A knowledge check attached to exactly one lesson."""

    __tablename__ = "quizzes"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("lessons.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    instructions: Mapped[str | None] = mapped_column(Text)
    passing_score: Mapped[int] = mapped_column(Integer, default=70, nullable=False)  # percent
    max_attempts: Mapped[int | None] = mapped_column(Integer)  # NULL = unlimited
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    shuffle_questions: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    lesson: Mapped[Lesson] = relationship(back_populates="quiz")
    questions: Mapped[list[QuizQuestion]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan", order_by="QuizQuestion.order_index"
    )
    attempts: Mapped[list[QuizAttempt]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )


class QuizQuestion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One question. Correct answers live on options or in `answer_key`."""

    __tablename__ = "quiz_questions"
    __table_args__ = (Index("ix_quiz_questions_quiz_order", "quiz_id", "order_index"),)

    quiz_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("quizzes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(
        enum_column(QuestionType, length=24), nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(Text)
    # For question types without discrete options (fill-blank, subnet-calc,
    # cli-command) this carries the expected value and matching rules.
    answer_key: Mapped[dict[str, Any] | None] = mapped_column(JSONColumn)
    media_url: Mapped[str | None] = mapped_column(String(512))
    points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    quiz: Mapped[Quiz] = relationship(back_populates="questions")
    options: Mapped[list[QuizOption]] = relationship(
        back_populates="question", cascade="all, delete-orphan", order_by="QuizOption.order_index"
    )


class QuizOption(UUIDPrimaryKeyMixin, Base):
    """A selectable answer for choice-style questions."""

    __tablename__ = "quiz_options"

    question_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("quiz_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    question: Mapped[QuizQuestion] = relationship(back_populates="options")
