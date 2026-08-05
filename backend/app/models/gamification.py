"""Achievements, XP ledger, and certificates."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONColumn, enum_column
from app.models.enums import AchievementCategory, XPReason

if TYPE_CHECKING:
    from app.models.catalog import Course
    from app.models.user import User


class Achievement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An earnable badge defined by a declarative criteria document."""

    __tablename__ = "achievements"

    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[AchievementCategory] = mapped_column(
        enum_column(AchievementCategory, length=20), nullable=False
    )
    # Evaluated by the achievement engine, e.g.
    # {"metric": "labs_completed", "operator": ">=", "value": 10}
    criteria: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict, nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Hidden achievements are revealed only once earned.
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    awards: Mapped[list[UserAchievement]] = relationship(
        back_populates="achievement", cascade="all, delete-orphan"
    )


class UserAchievement(UUIDPrimaryKeyMixin, Base):
    """Join row recording that a user earned an achievement."""

    __tablename__ = "user_achievements"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "achievement_id", name="uq_user_achievements_user_id_achievement_id"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="achievements")
    achievement: Mapped[Achievement] = relationship(back_populates="awards")


class XPTransaction(UUIDPrimaryKeyMixin, Base):
    """Append-only ledger of every XP grant.

    `UserStats.total_xp` is the running sum. Keeping the ledger means a
    corrupted counter can always be rebuilt, and it powers "XP earned this
    week" style leaderboards that a single total cannot answer.
    """

    __tablename__ = "xp_transactions"
    __table_args__ = (Index("ix_xp_transactions_user_created", "user_id", "created_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[XPReason] = mapped_column(enum_column(XPReason, length=32), nullable=False)
    # Soft reference to the originating entity (lesson, lab, quiz...). Not a
    # foreign key: the ledger must survive deletion of the content it refers to.
    reference_type: Mapped[str | None] = mapped_column(String(40))
    reference_id: Mapped[uuid.UUID | None] = mapped_column(GUID())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="xp_transactions")


class Certificate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A course completion certificate with a public verification code."""

    __tablename__ = "certificates"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_certificates_user_id_course_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    course_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    serial: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    # Shared publicly to prove authenticity; separate from the internal serial.
    verification_code: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    recipient_name: Mapped[str] = mapped_column(String(160), nullable=False)
    final_score: Mapped[int | None] = mapped_column(Integer)
    pdf_url: Mapped[str | None] = mapped_column(String(512))
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="certificates")
    course: Mapped[Course] = relationship(back_populates="certificates")
