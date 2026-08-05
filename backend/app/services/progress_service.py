"""Learner progress: XP, levels, and study streaks.

This is the engine every later part feeds. Parts 3, 8 and 9 call
:meth:`ProgressService.grant_xp` when a lesson, lab or quiz completes; nothing
else is permitted to write `user_stats.total_xp` directly.

Two invariants hold the design together:

1. **The ledger is the truth.** `xp_transactions` is append-only;
   `user_stats.total_xp` is a cache of its sum and is always rebuildable via
   :meth:`recalculate_stats`.
2. **XP is granted once per source.** Re-completing a lesson must not pay
   again, so grants carry a reference and are deduplicated against it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import as_utc, utcnow
from app.core.logging import get_logger
from app.models.enums import XPReason
from app.models.gamification import XPTransaction
from app.models.user import User, UserStats
from app.repositories.progress import XPTransactionRepository
from app.repositories.user import UserStatsRepository

logger = get_logger(__name__)

# Level curve. Level N requires BASE * (N-1)^EXPONENT total XP, which spaces
# early levels closely (fast early feedback) and stretches later ones.
LEVEL_BASE_XP = 100
LEVEL_EXPONENT = 1.5
MAX_LEVEL = 100


def xp_required_for_level(level: int) -> int:
    """Total XP needed to have reached `level`."""
    if level <= 1:
        return 0
    return int(LEVEL_BASE_XP * ((level - 1) ** LEVEL_EXPONENT))


def level_for_xp(total_xp: int) -> int:
    """Highest level fully paid for by `total_xp`."""
    if total_xp < LEVEL_BASE_XP:
        return 1
    level = 1
    while level < MAX_LEVEL and xp_required_for_level(level + 1) <= total_xp:
        level += 1
    return level


@dataclass(frozen=True, slots=True)
class LevelProgress:
    """Where a learner sits between their current and next level."""

    level: int
    total_xp: int
    current_level_xp: int
    next_level_xp: int
    xp_into_level: int
    xp_for_next_level: int
    percent_to_next_level: float
    is_max_level: bool


def describe_level(total_xp: int) -> LevelProgress:
    """Expand a raw XP total into everything a progress bar needs."""
    level = level_for_xp(total_xp)
    current_threshold = xp_required_for_level(level)
    is_max = level >= MAX_LEVEL
    next_threshold = current_threshold if is_max else xp_required_for_level(level + 1)

    span = max(next_threshold - current_threshold, 1)
    into = total_xp - current_threshold

    return LevelProgress(
        level=level,
        total_xp=total_xp,
        current_level_xp=current_threshold,
        next_level_xp=next_threshold,
        xp_into_level=into,
        xp_for_next_level=0 if is_max else span,
        percent_to_next_level=100.0 if is_max else round(min(into / span, 1.0) * 100, 1),
        is_max_level=is_max,
    )


@dataclass(frozen=True, slots=True)
class XPGrant:
    """Outcome of an XP award."""

    awarded: int
    total_xp: int
    level: int
    leveled_up: bool
    was_duplicate: bool


class ProgressService:
    """Owns every write to a learner's progress counters."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.stats = UserStatsRepository(session)
        self.xp = XPTransactionRepository(session)

    async def stats_for(self, user: User) -> UserStats:
        """Return the user's stats row, creating it if an old account lacks one.

        Public because sibling services (lesson and quiz completion) increment
        their own counters — `lessons_completed`, `quizzes_passed` — on the same
        row inside the same transaction.
        """
        stats = await self.stats.get_for_user(user.id)
        if stats is None:
            stats = UserStats(user_id=user.id)
            self.stats.add(stats)
            await self.session.flush()
        return stats

    # ------------------------------------------------------------------ #
    # XP
    # ------------------------------------------------------------------ #
    async def grant_xp(
        self,
        user: User,
        amount: int,
        reason: XPReason,
        *,
        reference_type: str | None = None,
        reference_id: uuid.UUID | None = None,
        commit: bool = True,
    ) -> XPGrant:
        """Award XP, writing a ledger row and updating the cached total.

        When `reference_type` and `reference_id` are supplied the grant is
        idempotent for that source: finishing the same lesson twice pays once.
        """
        stats = await self.stats_for(user)

        if reference_type is not None and reference_id is not None:
            already = await self.xp.exists_for_reference(
                user.id, reason, reference_type, reference_id
            )
            if already:
                return XPGrant(
                    awarded=0,
                    total_xp=stats.total_xp,
                    level=stats.level,
                    leveled_up=False,
                    was_duplicate=True,
                )

        previous_level = stats.level

        self.xp.add(
            XPTransaction(
                user_id=user.id,
                amount=amount,
                reason=reason,
                reference_type=reference_type,
                reference_id=reference_id,
            )
        )

        stats.total_xp += amount
        stats.level = level_for_xp(stats.total_xp)

        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

        leveled_up = stats.level > previous_level
        if leveled_up:
            logger.info(
                "Learner levelled up",
                extra={"user_id": str(user.id), "level": stats.level},
            )

        return XPGrant(
            awarded=amount,
            total_xp=stats.total_xp,
            level=stats.level,
            leveled_up=leveled_up,
            was_duplicate=False,
        )

    # ------------------------------------------------------------------ #
    # Streaks and activity
    # ------------------------------------------------------------------ #
    async def record_activity(
        self, user: User, *, study_seconds: int = 0, commit: bool = True
    ) -> UserStats:
        """Register study activity for today and roll the streak forward.

        Streaks are counted in **calendar days in the user's own timezone**, not
        24-hour periods: someone studying at 23:00 and again at 08:00 has
        practised on two days and expects a streak of two.
        """
        stats = await self.stats_for(user)
        today = self._local_today(user)
        last_active = (
            as_utc(stats.last_activity_date).date()
            if stats.last_activity_date is not None
            else None
        )

        if last_active is None:
            stats.current_streak_days = 1
        elif last_active == today:
            pass  # already counted today
        elif last_active == today - timedelta(days=1):
            stats.current_streak_days += 1
        else:
            stats.current_streak_days = 1  # a day was missed

        stats.longest_streak_days = max(stats.longest_streak_days, stats.current_streak_days)
        stats.last_activity_date = utcnow()
        if study_seconds > 0:
            stats.total_study_seconds += study_seconds

        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return stats

    @staticmethod
    def _local_today(user: User) -> date:
        """Today's date in the learner's configured timezone."""
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            return utcnow().astimezone(ZoneInfo(user.timezone)).date()
        except (ZoneInfoNotFoundError, ValueError):
            # A bad timezone string must not break streak accounting.
            return utcnow().date()

    async def current_streak(self, user: User) -> int:
        """The streak as of now, treating a missed day as broken.

        The stored counter is only refreshed on activity, so reading it
        directly would show a stale streak to someone who has not studied for a
        week. This does not write; the next `record_activity` resets it.
        """
        stats = await self.stats_for(user)
        if stats.last_activity_date is None:
            return 0

        today = self._local_today(user)
        last_active = as_utc(stats.last_activity_date).date()
        if last_active in (today, today - timedelta(days=1)):
            return stats.current_streak_days
        return 0

    # ------------------------------------------------------------------ #
    # Repair
    # ------------------------------------------------------------------ #
    async def recalculate_stats(self, user: User) -> UserStats:
        """Rebuild cached counters from the ledger.

        The cache exists for read performance and can drift if a write path
        ever fails midway. This restores it from the append-only source of
        truth, and is what makes caching safe in the first place.
        """
        stats = await self.stats_for(user)
        stats.total_xp = await self.xp.total_for_user(user.id)
        stats.level = level_for_xp(stats.total_xp)
        await self.session.commit()
        logger.info(
            "Recalculated learner stats",
            extra={"user_id": str(user.id), "total_xp": stats.total_xp},
        )
        return stats
