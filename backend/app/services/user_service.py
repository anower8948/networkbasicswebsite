"""User profile and progress-summary use cases."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.exceptions import UserNotFound, ValidationError
from app.core.logging import get_logger
from app.models.user import User, UserStats
from app.repositories.progress import XPTransactionRepository
from app.repositories.user import RefreshTokenRepository, UserRepository, UserStatsRepository
from app.schemas.progress import (
    LevelProgressRead,
    ProgressSummary,
    XPTransactionRead,
)
from app.schemas.user import UserUpdate
from app.services.progress_service import ProgressService, describe_level

logger = get_logger(__name__)

# Kept small: the dashboard shows a short activity feed, not a full history.
RECENT_XP_LIMIT = 10


class UserService:
    """Read and update user profiles, and assemble progress views."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.stats = UserStatsRepository(session)
        self.xp = XPTransactionRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.progress = ProgressService(session)

    # ------------------------------------------------------------------ #
    # Profile
    # ------------------------------------------------------------------ #
    async def get_profile(self, user_id: uuid.UUID) -> User:
        user = await self.users.get_with_stats(user_id)
        if user is None:
            raise UserNotFound()
        return user

    async def update_profile(self, user: User, payload: UserUpdate) -> User:
        """Apply a partial profile update.

        `exclude_unset` is essential: without it every omitted optional field
        would arrive as `None` and blank out data the client never mentioned.
        """
        changes = payload.model_dump(exclude_unset=True)

        if "timezone" in changes and changes["timezone"] is not None:
            self._validate_timezone(changes["timezone"])

        for field, value in changes.items():
            setattr(user, field, value)

        await self.session.commit()
        await self.session.refresh(user)
        return user

    @staticmethod
    def _validate_timezone(name: str) -> None:
        """Reject unknown timezones at the boundary.

        Streak calculation resolves this string on every activity ping; storing
        an invalid one would silently fall back to UTC and miscount streaks for
        that learner indefinitely.
        """
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError(
                f"'{name}' is not a recognised IANA timezone.",
                details={"fields": {"timezone": "Unknown timezone."}},
            ) from exc

    async def deactivate(self, user: User) -> None:
        """Self-service account deactivation.

        A soft flag rather than a delete: certificates, lab attempts and the XP
        ledger must survive, and a deleted row would cascade them away. Login is
        refused and every session is revoked immediately.
        """
        user.is_active = False
        user.tokens_valid_from = utcnow()
        await self.refresh_tokens.revoke_all_for_user(user.id)
        await self.session.commit()
        logger.info("Account deactivated", extra={"user_id": str(user.id)})

    # ------------------------------------------------------------------ #
    # Progress
    # ------------------------------------------------------------------ #
    async def ensure_stats(self, user: User) -> UserStats:
        stats = await self.stats.get_for_user(user.id)
        if stats is None:
            stats = UserStats(user_id=user.id)
            self.stats.add(stats)
            await self.session.commit()
            await self.session.refresh(stats)
        return stats

    async def progress_summary(self, user: User) -> ProgressSummary:
        """Assemble the dashboard payload in one round trip."""
        stats = await self.ensure_stats(user)
        level = describe_level(stats.total_xp)

        week_start = utcnow() - timedelta(days=7)
        xp_this_week = await self.xp.sum_since(user.id, week_start)
        recent = await self.xp.recent_for_user(user.id, limit=RECENT_XP_LIMIT)

        # Read the live streak rather than the stored counter, which is only
        # refreshed on activity and would show a stale value after a break.
        streak = await self.progress.current_streak(user)

        return ProgressSummary(
            total_xp=stats.total_xp,
            level=LevelProgressRead(
                level=level.level,
                total_xp=level.total_xp,
                current_level_xp=level.current_level_xp,
                next_level_xp=level.next_level_xp,
                xp_into_level=level.xp_into_level,
                xp_for_next_level=level.xp_for_next_level,
                percent_to_next_level=level.percent_to_next_level,
                is_max_level=level.is_max_level,
            ),
            lessons_completed=stats.lessons_completed,
            courses_completed=stats.courses_completed,
            labs_completed=stats.labs_completed,
            quizzes_passed=stats.quizzes_passed,
            total_study_seconds=stats.total_study_seconds,
            current_streak_days=streak,
            longest_streak_days=stats.longest_streak_days,
            xp_this_week=xp_this_week,
            last_activity_at=stats.last_activity_date,
            recent_xp=[XPTransactionRead.model_validate(entry) for entry in recent],
        )

    async def leaderboard(self, *, limit: int = 20, offset: int = 0) -> Sequence[UserStats]:
        """Top learners by XP. Surfaced to users in Part 9."""
        return await self.stats.leaderboard(limit=limit, offset=offset)
