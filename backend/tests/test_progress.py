"""Tests for the XP, level, and streak engine."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.security import hash_password
from app.models.enums import XPReason
from app.models.user import User, UserStats
from app.services.progress_service import (
    MAX_LEVEL,
    ProgressService,
    describe_level,
    level_for_xp,
    xp_required_for_level,
)


class TestLevelCurve:
    def test_starts_at_level_one(self) -> None:
        assert level_for_xp(0) == 1
        assert xp_required_for_level(1) == 0

    def test_level_rises_with_xp(self) -> None:
        assert level_for_xp(100) == 2
        assert level_for_xp(50_000) > level_for_xp(5_000)

    def test_thresholds_increase_monotonically(self) -> None:
        thresholds = [xp_required_for_level(level) for level in range(1, 30)]
        assert thresholds == sorted(thresholds)
        assert len(set(thresholds)) == len(thresholds)

    def test_each_level_costs_more_than_the_last(self) -> None:
        """The curve must stretch, or high levels become trivial to reach."""
        early = xp_required_for_level(3) - xp_required_for_level(2)
        late = xp_required_for_level(30) - xp_required_for_level(29)
        assert late > early

    def test_level_is_capped(self) -> None:
        assert level_for_xp(10**12) == MAX_LEVEL

    def test_describe_level_reports_progress_within_a_level(self) -> None:
        progress = describe_level(150)
        assert progress.level == 2
        assert progress.current_level_xp <= 150 < progress.next_level_xp
        assert 0 <= progress.percent_to_next_level <= 100
        assert not progress.is_max_level

    def test_describe_level_handles_the_cap(self) -> None:
        progress = describe_level(10**12)
        assert progress.is_max_level
        assert progress.percent_to_next_level == 100.0
        # Must not advertise a next level that does not exist.
        assert progress.xp_for_next_level == 0

    def test_percent_never_exceeds_one_hundred(self) -> None:
        for xp in (0, 1, 99, 100, 101, 5_000, 999_999):
            assert 0 <= describe_level(xp).percent_to_next_level <= 100


@pytest.fixture
async def learner(session: AsyncSession) -> User:
    user = User(
        email="progress@example.com",
        username="progress",
        hashed_password=hash_password("Subnetting2024"),
        timezone="UTC",
    )
    user.stats = UserStats()
    session.add(user)
    await session.commit()
    return user


class TestXPGrants:
    async def test_grant_increases_the_total(self, session: AsyncSession, learner: User) -> None:
        service = ProgressService(session)
        result = await service.grant_xp(learner, 40, XPReason.LESSON_COMPLETED)

        assert result.awarded == 40
        assert result.total_xp == 40
        assert not result.was_duplicate

    async def test_grants_accumulate(self, session: AsyncSession, learner: User) -> None:
        service = ProgressService(session)
        await service.grant_xp(learner, 30, XPReason.LESSON_COMPLETED)
        result = await service.grant_xp(learner, 25, XPReason.QUIZ_PASSED)

        assert result.total_xp == 55

    async def test_the_same_source_pays_only_once(
        self, session: AsyncSession, learner: User
    ) -> None:
        """Re-completing a lesson must not award XP again."""
        service = ProgressService(session)
        lesson_id = uuid.uuid4()

        first = await service.grant_xp(
            learner,
            50,
            XPReason.LESSON_COMPLETED,
            reference_type="lesson",
            reference_id=lesson_id,
        )
        second = await service.grant_xp(
            learner,
            50,
            XPReason.LESSON_COMPLETED,
            reference_type="lesson",
            reference_id=lesson_id,
        )

        assert first.awarded == 50
        assert second.awarded == 0
        assert second.was_duplicate
        assert second.total_xp == 50

    async def test_different_sources_both_pay(self, session: AsyncSession, learner: User) -> None:
        service = ProgressService(session)
        for _ in range(2):
            await service.grant_xp(
                learner,
                20,
                XPReason.LESSON_COMPLETED,
                reference_type="lesson",
                reference_id=uuid.uuid4(),
            )
        stats = await service.stats.get_for_user(learner.id)
        assert stats is not None
        assert stats.total_xp == 40

    async def test_reports_a_level_up(self, session: AsyncSession, learner: User) -> None:
        service = ProgressService(session)
        result = await service.grant_xp(learner, 250, XPReason.COURSE_COMPLETED)

        assert result.leveled_up
        assert result.level > 1

    async def test_stats_rebuild_from_the_ledger(
        self, session: AsyncSession, learner: User
    ) -> None:
        """The cached total must be recoverable from the append-only ledger."""
        service = ProgressService(session)
        await service.grant_xp(learner, 60, XPReason.LESSON_COMPLETED)
        await service.grant_xp(learner, 40, XPReason.LAB_COMPLETED)

        stats = await service.stats.get_for_user(learner.id)
        assert stats is not None
        stats.total_xp = 99999  # simulate drift
        await session.commit()

        repaired = await service.recalculate_stats(learner)
        assert repaired.total_xp == 100


class TestStreaks:
    async def test_first_activity_starts_a_streak(
        self, session: AsyncSession, learner: User
    ) -> None:
        stats = await ProgressService(session).record_activity(learner)
        assert stats.current_streak_days == 1
        assert stats.longest_streak_days == 1

    async def test_two_pings_on_one_day_count_once(
        self, session: AsyncSession, learner: User
    ) -> None:
        service = ProgressService(session)
        await service.record_activity(learner)
        stats = await service.record_activity(learner)
        assert stats.current_streak_days == 1

    async def test_consecutive_days_extend_the_streak(
        self, session: AsyncSession, learner: User
    ) -> None:
        service = ProgressService(session)
        stats = await service.record_activity(learner)

        stats.last_activity_date = utcnow() - timedelta(days=1)
        await session.commit()

        stats = await service.record_activity(learner)
        assert stats.current_streak_days == 2

    async def test_a_missed_day_resets_the_streak(
        self, session: AsyncSession, learner: User
    ) -> None:
        service = ProgressService(session)
        stats = await service.record_activity(learner)
        stats.current_streak_days = 9
        stats.longest_streak_days = 9
        stats.last_activity_date = utcnow() - timedelta(days=3)
        await session.commit()

        stats = await service.record_activity(learner)
        assert stats.current_streak_days == 1
        # The record must survive the reset.
        assert stats.longest_streak_days == 9

    async def test_current_streak_reads_zero_after_a_break(
        self, session: AsyncSession, learner: User
    ) -> None:
        """The stored counter is stale between sessions; the read must not be."""
        service = ProgressService(session)
        stats = await service.record_activity(learner)
        stats.current_streak_days = 12
        stats.last_activity_date = utcnow() - timedelta(days=5)
        await session.commit()

        assert await service.current_streak(learner) == 0

    async def test_study_time_accumulates(self, session: AsyncSession, learner: User) -> None:
        service = ProgressService(session)
        await service.record_activity(learner, study_seconds=300)
        stats = await service.record_activity(learner, study_seconds=180)
        assert stats.total_study_seconds == 480

    async def test_an_invalid_timezone_does_not_break_streaks(
        self, session: AsyncSession, learner: User
    ) -> None:
        """A bad stored timezone must degrade to UTC, not raise."""
        learner.timezone = "Not/AZone"
        await session.commit()

        stats = await ProgressService(session).record_activity(learner)
        assert stats.current_streak_days == 1
