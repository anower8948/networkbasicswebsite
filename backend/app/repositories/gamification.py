"""Queries over achievements, certificates, and the XP ledger for leaderboards."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import Row, func, select
from sqlalchemy.orm import selectinload

from app.models.catalog import Course
from app.models.enums import AttemptStatus
from app.models.gamification import Achievement, Certificate, UserAchievement, XPTransaction
from app.models.lab import LabAttempt, Topology
from app.models.user import User, UserStats
from app.repositories.base import BaseRepository


class AchievementRepository(BaseRepository[Achievement]):
    model = Achievement

    async def list_active(self) -> Sequence[Achievement]:
        result = await self.session.execute(
            select(Achievement)
            .where(Achievement.is_active.is_(True))
            .order_by(Achievement.category, Achievement.title)
        )
        return result.scalars().all()

    async def get_by_slug(self, slug: str) -> Achievement | None:
        result = await self.session.execute(select(Achievement).where(Achievement.slug == slug))
        return result.scalar_one_or_none()


class UserAchievementRepository(BaseRepository[UserAchievement]):
    model = UserAchievement

    async def earned_at_by_achievement(self, user_id: uuid.UUID) -> dict[uuid.UUID, datetime]:
        result = await self.session.execute(
            select(UserAchievement.achievement_id, UserAchievement.earned_at).where(
                UserAchievement.user_id == user_id
            )
        )
        return {row[0]: row[1] for row in result.all()}


class CertificateRepository(BaseRepository[Certificate]):
    model = Certificate

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Certificate]:
        result = await self.session.execute(
            select(Certificate)
            .options(selectinload(Certificate.course))
            .where(Certificate.user_id == user_id)
            .order_by(Certificate.issued_at.desc())
        )
        return result.scalars().all()

    async def get_for_user_course(
        self, user_id: uuid.UUID, course_id: uuid.UUID
    ) -> Certificate | None:
        result = await self.session.execute(
            select(Certificate).where(
                Certificate.user_id == user_id, Certificate.course_id == course_id
            )
        )
        return result.scalar_one_or_none()

    async def get_by_verification_code(self, code: str) -> Certificate | None:
        """Load a certificate for public verification, with what it needs to
        answer: the course and the holder."""
        result = await self.session.execute(
            select(Certificate)
            .options(selectinload(Certificate.course), selectinload(Certificate.user))
            .where(Certificate.verification_code == code)
        )
        return result.scalar_one_or_none()

    async def serial_exists(self, serial: str) -> bool:
        result = await self.session.execute(
            select(Certificate.id).where(Certificate.serial == serial).limit(1)
        )
        return result.first() is not None


class LeaderboardRepository(BaseRepository[UserStats]):
    model = UserStats

    async def top_all_time(self, limit: int) -> Sequence[Row[tuple[User, UserStats]]]:
        """Ranked by the cached total — this is what the descending index on
        `user_stats.total_xp` exists for."""
        result = await self.session.execute(
            select(User, UserStats)
            .join(UserStats, UserStats.user_id == User.id)
            .where(User.is_active.is_(True))
            .order_by(UserStats.total_xp.desc(), User.created_at)
            .limit(limit)
        )
        return result.all()

    async def top_since(self, since: datetime, limit: int) -> Sequence[Row[tuple[User, int, int]]]:
        """Ranked by XP earned since a date — answerable only from the ledger.

        This is why `xp_transactions` is append-only rather than just a counter:
        a running total cannot say what someone earned this week.
        """
        earned = func.coalesce(func.sum(XPTransaction.amount), 0).label("earned")
        result = await self.session.execute(
            select(User, earned, UserStats.level)
            .join(XPTransaction, XPTransaction.user_id == User.id)
            .join(UserStats, UserStats.user_id == User.id)
            .where(User.is_active.is_(True), XPTransaction.created_at >= since)
            .group_by(User.id, UserStats.level)
            .order_by(earned.desc(), User.created_at)
            .limit(limit)
        )
        return result.all()

    async def xp_since(self, user_id: uuid.UUID, since: datetime) -> int:
        result = await self.session.execute(
            select(func.coalesce(func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == user_id, XPTransaction.created_at >= since
            )
        )
        return int(result.scalar_one())

    async def rank_all_time(self, total_xp: int) -> int:
        """How many active learners are ahead — one count, not a full sort."""
        result = await self.session.execute(
            select(func.count())
            .select_from(UserStats)
            .join(User, User.id == UserStats.user_id)
            .where(User.is_active.is_(True), UserStats.total_xp > total_xp)
        )
        return int(result.scalar_one()) + 1


class MetricRepository(BaseRepository[UserStats]):
    """The counts an achievement can test that `user_stats` does not cache."""

    model = UserStats

    async def perfect_labs(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(func.distinct(LabAttempt.lab_id))).where(
                LabAttempt.user_id == user_id,
                LabAttempt.status == AttemptStatus.PASSED,
                LabAttempt.score_percent >= 100,
            )
        )
        return int(result.scalar_one())

    async def topologies_saved(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(Topology.id)).where(Topology.owner_id == user_id)
        )
        return int(result.scalar_one())

    async def completed_course_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        from app.models.enums import EnrollmentStatus
        from app.models.progress import Enrollment

        result = await self.session.execute(
            select(Enrollment.course_id).where(
                Enrollment.user_id == user_id,
                Enrollment.status == EnrollmentStatus.COMPLETED,
            )
        )
        return {row[0] for row in result.all()}

    async def courses_granting_certificates(self) -> Sequence[Course]:
        result = await self.session.execute(
            select(Course).where(Course.grants_certificate.is_(True))
        )
        return result.scalars().all()
