"""User identity, learner statistics, and authentication artefacts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, enum_column
from app.models.enums import TokenPurpose, UserRole

if TYPE_CHECKING:
    from app.models.gamification import Certificate, UserAchievement, XPTransaction
    from app.models.lab import LabAttempt, Topology
    from app.models.progress import Bookmark, Enrollment, LessonProgress, Note


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An authenticated account.

    Holds identity and authorisation only. Learning counters live on
    :class:`UserStats` so that the hot auth path never loads gamification data,
    and so leaderboard writes do not contend with profile reads.
    """

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    full_name: Mapped[str | None] = mapped_column(String(120))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    bio: Mapped[str | None] = mapped_column(Text)
    country: Mapped[str | None] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole, length=20),
        default=UserRole.STUDENT,
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Any access token issued before this instant is rejected. Bumped on
    # password change so a stolen access token dies immediately rather than
    # living out its remaining TTL.
    tokens_valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    stats: Mapped[UserStats] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    verification_tokens: Mapped[list[VerificationToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    enrollments: Mapped[list[Enrollment]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    lesson_progress: Mapped[list[LessonProgress]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    notes: Mapped[list[Note]] = relationship(back_populates="user", cascade="all, delete-orphan")
    bookmarks: Mapped[list[Bookmark]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    topologies: Mapped[list[Topology]] = relationship(
        back_populates="owner", cascade="all, delete-orphan"
    )
    lab_attempts: Mapped[list[LabAttempt]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    achievements: Mapped[list[UserAchievement]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    certificates: Mapped[list[Certificate]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    xp_transactions: Mapped[list[XPTransaction]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        return self.full_name or self.username


class UserStats(TimestampMixin, Base):
    """Denormalised learning counters for dashboards and leaderboards.

    These are derived values, rebuildable from `xp_transactions`,
    `lesson_progress`, and `lab_attempts`. They exist because rendering the
    dashboard or a leaderboard page from those source tables would require
    several aggregate scans per request.
    """

    __tablename__ = "user_stats"
    __table_args__ = (
        # Leaderboard reads are "top N by XP" — a descending index answers them
        # without sorting the table.
        Index("ix_user_stats_total_xp_desc", "total_xp"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    total_xp: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lessons_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    courses_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    labs_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quizzes_passed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_study_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    longest_streak_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_activity_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="stats")


class RefreshToken(UUIDPrimaryKeyMixin, Base):
    """A single issued refresh token.

    Only the SHA-256 digest is stored. Tokens are rotated on every use: the old
    row is revoked and linked to its replacement via `replaced_by_id`. All rows
    from one login share a `family_id`, so presenting an already-revoked token
    (a replay, meaning the token leaked) lets us revoke the whole family at once.
    """

    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_tokens_user_family", "user_id", "family_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(GUID(), nullable=False)

    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("refresh_tokens.id", ondelete="SET NULL")
    )

    user_agent: Mapped[str | None] = mapped_column(String(400))
    ip_address: Mapped[str | None] = mapped_column(String(45))  # fits IPv6

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None


class VerificationToken(UUIDPrimaryKeyMixin, Base):
    """Single-use token for email verification and password reset.

    Wired up in Part 2 alongside outbound email; the table is defined here so
    the initial migration covers the whole authentication domain.
    """

    __tablename__ = "verification_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    purpose: Mapped[TokenPurpose] = mapped_column(
        enum_column(TokenPurpose, length=32), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="verification_tokens")
