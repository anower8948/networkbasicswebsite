"""The achievement engine.

Badges are **data**, not code: each carries a declarative criteria document that
is evaluated against a single snapshot of the learner's metrics. Two things
follow from that, and both are the reason for the design:

* Adding a badge is a seed row, not a deployment.
* Every badge is evaluated against **one** snapshot, so awarding fifteen badges
  costs the same handful of queries as awarding one. A per-badge callback design
  would have run its own queries fifteen times.

Evaluation is idempotent. It is called after each XP-earning event, and the
unique constraint on `(user_id, achievement_id)` is the real guard — the
in-memory check is just to avoid pointless inserts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.logging import get_logger
from app.models.enums import XPReason
from app.models.gamification import Achievement, UserAchievement
from app.models.user import User
from app.repositories.gamification import (
    AchievementRepository,
    MetricRepository,
    UserAchievementRepository,
)
from app.schemas.gamification import (
    AchievementCriteria,
    AchievementList,
    AchievementRead,
    AllOfCriteria,
    MetricCriterion,
)
from app.services.progress_service import ProgressService

logger = get_logger(__name__)

_CRITERIA: TypeAdapter[AchievementCriteria] = TypeAdapter(AchievementCriteria)


@dataclass(frozen=True, slots=True)
class MetricSnapshot:
    """Every metric an achievement may test, gathered once."""

    total_xp: int
    level: int
    lessons_completed: int
    courses_completed: int
    labs_completed: int
    quizzes_passed: int
    current_streak_days: int
    longest_streak_days: int
    perfect_labs: int
    topologies_saved: int
    study_minutes: int

    def value_of(self, metric: str) -> int:
        return int(getattr(self, metric))


class AchievementService:
    """Awards badges and reports progress toward the unearned ones."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.achievements = AchievementRepository(session)
        self.awards = UserAchievementRepository(session)
        self.metrics = MetricRepository(session)
        self.progress = ProgressService(session)

    # ------------------------------------------------------------------ #
    # Snapshot
    # ------------------------------------------------------------------ #
    async def snapshot(self, user: User) -> MetricSnapshot:
        stats = await self.progress.stats_for(user)
        return MetricSnapshot(
            total_xp=stats.total_xp,
            level=stats.level,
            lessons_completed=stats.lessons_completed,
            courses_completed=stats.courses_completed,
            labs_completed=stats.labs_completed,
            quizzes_passed=stats.quizzes_passed,
            # The *live* streak, not the stored counter: a badge for a 7-day
            # streak must not be awarded to someone whose streak lapsed weeks
            # ago and whose counter was never refreshed.
            current_streak_days=await self.progress.current_streak(user),
            longest_streak_days=stats.longest_streak_days,
            perfect_labs=await self.metrics.perfect_labs(user.id),
            topologies_saved=await self.metrics.topologies_saved(user.id),
            study_minutes=stats.total_study_seconds // 60,
        )

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    async def evaluate(self, user: User, *, commit: bool = True) -> list[AchievementRead]:
        """Award every badge the learner now qualifies for.

        Returns only what was *newly* earned, so a caller can show it. XP for a
        badge is granted here, which is why this is never called from inside
        `grant_xp` — that would recurse.
        """
        catalog = await self.achievements.list_active()
        already = await self.awards.earned_at_by_achievement(user.id)
        metrics = await self.snapshot(user)

        newly: list[Achievement] = []
        for achievement in catalog:
            if achievement.id in already:
                continue
            if not self._satisfied(achievement, metrics):
                continue

            self.awards.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
            newly.append(achievement)

        if not newly:
            return []

        await self.session.flush()

        for achievement in newly:
            if achievement.xp_reward > 0:
                await self.progress.grant_xp(
                    user,
                    achievement.xp_reward,
                    XPReason.ACHIEVEMENT_EARNED,
                    reference_type="achievement",
                    reference_id=achievement.id,
                    commit=False,
                )

        if commit:
            await self.session.commit()

        logger.info(
            "Achievements earned",
            extra={"user_id": str(user.id), "slugs": [item.slug for item in newly]},
        )
        now = utcnow()
        return [self._read(item, earned_at=now, metrics=metrics) for item in newly]

    # ------------------------------------------------------------------ #
    # Listing
    # ------------------------------------------------------------------ #
    async def list_for_user(self, user: User) -> AchievementList:
        catalog = await self.achievements.list_active()
        earned = await self.awards.earned_at_by_achievement(user.id)
        metrics = await self.snapshot(user)

        items = [
            self._read(item, earned_at=earned.get(item.id), metrics=metrics)
            for item in catalog
            # A secret badge stays out of the list until it is earned; showing
            # it greyed out with its title would defeat the point of it.
            if not item.is_secret or item.id in earned
        ]
        return AchievementList(
            items=items,
            earned_count=sum(1 for item in items if item.earned),
            total_count=len(items),
        )

    # ------------------------------------------------------------------ #
    # Criteria
    # ------------------------------------------------------------------ #
    def _satisfied(self, achievement: Achievement, metrics: MetricSnapshot) -> bool:
        criteria = self._parse(achievement)
        if criteria is None:
            return False
        if isinstance(criteria, AllOfCriteria):
            return all(self._compare(item, metrics) for item in criteria.all_of)
        return self._compare(criteria, metrics)

    @staticmethod
    def _parse(achievement: Achievement) -> AchievementCriteria | None:
        try:
            return _CRITERIA.validate_python(achievement.criteria)
        except ValidationError:
            # A malformed badge must never award itself, and must never break
            # the page for every other badge either.
            logger.warning(
                "Achievement has unreadable criteria and was skipped",
                extra={"slug": achievement.slug},
            )
            return None

    @staticmethod
    def _compare(criterion: MetricCriterion, metrics: MetricSnapshot) -> bool:
        actual = metrics.value_of(criterion.metric)
        match criterion.operator:
            case ">=":
                return actual >= criterion.value
            case ">":
                return actual > criterion.value
            case "==":
                return actual == criterion.value
            case "<=":
                return actual <= criterion.value
            case "<":
                return actual < criterion.value

    def _progress_percent(self, achievement: Achievement, metrics: MetricSnapshot) -> float | None:
        """How close the learner is, as a percentage.

        Only meaningful for "reach N" style criteria, which is nearly all of
        them; anything else reports nothing rather than a misleading bar.
        """
        criteria = self._parse(achievement)
        if criteria is None:
            return None

        parts = criteria.all_of if isinstance(criteria, AllOfCriteria) else [criteria]
        ratios: list[float] = []
        for part in parts:
            if part.operator not in (">=", ">") or part.value <= 0:
                continue
            ratios.append(min(metrics.value_of(part.metric) / part.value, 1.0))

        if not ratios:
            return None
        # The slowest requirement is the one holding the badge up.
        return round(min(ratios) * 100, 1)

    def _read(
        self,
        achievement: Achievement,
        *,
        earned_at: datetime | None,
        metrics: MetricSnapshot,
    ) -> AchievementRead:
        earned = earned_at is not None
        return AchievementRead(
            id=achievement.id,
            slug=achievement.slug,
            title=achievement.title,
            description=achievement.description,
            icon=achievement.icon,
            category=achievement.category,
            xp_reward=achievement.xp_reward,
            earned=earned,
            earned_at=earned_at,
            progress_percent=100.0 if earned else self._progress_percent(achievement, metrics),
        )


async def award_new_achievements(session: AsyncSession, user: User) -> list[AchievementRead]:
    """Convenience for the completion services, which all end the same way.

    Kept as a function rather than another service dependency so that
    `learning_service`, `quiz_service` and `lab_service` gain one import each
    instead of a constructor argument.
    """
    return await AchievementService(session).evaluate(user)


__all__ = ["AchievementService", "MetricSnapshot", "award_new_achievements"]
