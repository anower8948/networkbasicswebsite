"""Tests for achievements, leaderboards, and certificates.

The recurring theme is that recognition must be **earned exactly once** and must
**not leak**: a badge cannot pay twice, a certificate cannot be issued twice,
and public verification must not expose anything a CV reader has no business
seeing.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import AchievementCategory
from app.models.gamification import Achievement
from app.models.user import User
from app.schemas.gamification import AchievementCriteria
from app.seeds.achievement_content import ACHIEVEMENTS
from app.services.achievement_service import AchievementService, MetricSnapshot

_CRITERIA: TypeAdapter[AchievementCriteria] = TypeAdapter(AchievementCriteria)

ENROLL = "/api/v1/courses/network-fundamentals/enroll"
# Only this course is marked `grants_certificate` in the seed data.
CERTIFIED_SLUG = "ipv4-addressing-subnetting"
CERTIFIED_ENROLL = f"/api/v1/courses/{CERTIFIED_SLUG}/enroll"


def snapshot(**overrides: int) -> MetricSnapshot:
    base: dict[str, int] = {
        "total_xp": 0,
        "level": 1,
        "lessons_completed": 0,
        "courses_completed": 0,
        "labs_completed": 0,
        "quizzes_passed": 0,
        "current_streak_days": 0,
        "longest_streak_days": 0,
        "perfect_labs": 0,
        "topologies_saved": 0,
        "study_minutes": 0,
    }
    base.update(overrides)
    return MetricSnapshot(**base)


async def make_user(session: AsyncSession, email: str = "badge@example.com") -> User:
    from app.core.security import hash_password

    user = User(
        email=email,
        username=email.split("@")[0],
        hashed_password=hash_password("Subnetting2024"),
        full_name="Badge Holder",
    )
    session.add(user)
    await session.commit()
    return user


async def add_achievement(session: AsyncSession, **overrides: Any) -> Achievement:
    achievement = Achievement(
        slug=overrides.pop("slug", "test-badge"),
        title=overrides.pop("title", "Test badge"),
        description=overrides.pop("description", "A badge."),
        category=overrides.pop("category", AchievementCategory.PROGRESS),
        criteria=overrides.pop(
            "criteria", {"metric": "lessons_completed", "operator": ">=", "value": 1}
        ),
        xp_reward=overrides.pop("xp_reward", 10),
        is_secret=overrides.pop("is_secret", False),
        is_active=overrides.pop("is_active", True),
    )
    session.add(achievement)
    await session.commit()
    return achievement


class TestSeededAchievements:
    @pytest.mark.parametrize("data", ACHIEVEMENTS, ids=lambda item: str(item["slug"]))
    def test_criteria_are_readable_by_the_engine(self, data: dict[str, Any]) -> None:
        """A badge naming an unknown metric would silently never award itself."""
        _CRITERIA.validate_python(data["criteria"])

    def test_slugs_are_unique(self) -> None:
        slugs = [item["slug"] for item in ACHIEVEMENTS]
        assert len(slugs) == len(set(slugs))

    def test_rewards_stay_modest(self) -> None:
        """A badge paying more than the work it recognises inverts the incentive."""
        assert all(item["xp_reward"] <= 150 for item in ACHIEVEMENTS)


class TestCriteriaEvaluation:
    async def test_a_threshold_is_met_exactly_at_the_boundary(self, session: AsyncSession) -> None:
        service = AchievementService(session)
        achievement = await add_achievement(
            session, criteria={"metric": "labs_completed", "operator": ">=", "value": 5}
        )

        assert service._satisfied(achievement, snapshot(labs_completed=5))
        assert not service._satisfied(achievement, snapshot(labs_completed=4))

    async def test_all_of_needs_every_part(self, session: AsyncSession) -> None:
        service = AchievementService(session)
        achievement = await add_achievement(
            session,
            criteria={
                "allOf": [
                    {"metric": "lessons_completed", "operator": ">=", "value": 5},
                    {"metric": "labs_completed", "operator": ">=", "value": 2},
                ]
            },
        )

        assert service._satisfied(achievement, snapshot(lessons_completed=5, labs_completed=2))
        assert not service._satisfied(achievement, snapshot(lessons_completed=9, labs_completed=1))

    async def test_unreadable_criteria_never_award(self, session: AsyncSession) -> None:
        """A malformed badge must fail closed, not award itself to everyone."""
        service = AchievementService(session)
        achievement = await add_achievement(
            session, criteria={"metric": "vibes", "operator": ">=", "value": 1}
        )

        assert not service._satisfied(achievement, snapshot(total_xp=999_999))

    async def test_progress_reports_the_slowest_requirement(self, session: AsyncSession) -> None:
        """Progress toward a compound badge is gated by whichever part lags."""
        service = AchievementService(session)
        achievement = await add_achievement(
            session,
            criteria={
                "allOf": [
                    {"metric": "lessons_completed", "operator": ">=", "value": 10},
                    {"metric": "labs_completed", "operator": ">=", "value": 10},
                ]
            },
        )

        percent = service._progress_percent(
            achievement, snapshot(lessons_completed=9, labs_completed=2)
        )
        assert percent == 20.0


class TestAwarding:
    async def test_a_qualifying_learner_earns_the_badge_and_its_xp(
        self, session: AsyncSession
    ) -> None:
        user = await make_user(session)
        await add_achievement(
            session,
            criteria={"metric": "total_xp", "operator": ">=", "value": 0},
            xp_reward=15,
        )
        service = AchievementService(session)

        earned = await service.evaluate(user)

        assert [item.slug for item in earned] == ["test-badge"]
        stats = await service.progress.stats_for(user)
        assert stats.total_xp == 15

    async def test_evaluating_twice_awards_once(self, session: AsyncSession) -> None:
        user = await make_user(session)
        await add_achievement(
            session, criteria={"metric": "total_xp", "operator": ">=", "value": 0}, xp_reward=15
        )
        service = AchievementService(session)

        await service.evaluate(user)
        second = await service.evaluate(user)

        assert second == []
        stats = await service.progress.stats_for(user)
        assert stats.total_xp == 15

    async def test_an_inactive_badge_is_never_awarded(self, session: AsyncSession) -> None:
        user = await make_user(session)
        await add_achievement(
            session,
            criteria={"metric": "total_xp", "operator": ">=", "value": 0},
            is_active=False,
        )

        assert await AchievementService(session).evaluate(user) == []

    async def test_a_secret_badge_is_hidden_until_earned(self, session: AsyncSession) -> None:
        user = await make_user(session)
        await add_achievement(
            session,
            slug="hidden",
            criteria={"metric": "total_xp", "operator": ">=", "value": 5000},
            is_secret=True,
        )
        service = AchievementService(session)

        listing = await service.list_for_user(user)

        assert [item.slug for item in listing.items] == []


@pytest.mark.usefixtures("seeded_catalog")
class TestAchievementEndpoints:
    async def test_the_list_shows_progress_toward_unearned_badges(
        self, authed_client: AsyncClient
    ) -> None:
        response = await authed_client.get("/api/v1/achievements")

        assert response.status_code == 200
        body = response.json()
        assert body["totalCount"] > 0
        assert body["earnedCount"] == 0
        assert all(item["progressPercent"] is not None for item in body["items"])

    async def test_completing_a_lesson_earns_a_badge(self, authed_client: AsyncClient) -> None:
        await authed_client.post(ENROLL)
        course = await authed_client.get("/api/v1/courses/network-fundamentals")
        lesson_id = course.json()["modules"][0]["lessons"][0]["id"]

        completion = await authed_client.post(f"/api/v1/lessons/{lesson_id}/complete")

        slugs = [item["slug"] for item in completion.json()["newAchievements"]]
        assert "first-steps" in slugs

    async def test_evaluate_is_idempotent(self, authed_client: AsyncClient) -> None:
        first = await authed_client.post("/api/v1/achievements/evaluate")
        second = await authed_client.post("/api/v1/achievements/evaluate")

        assert first.json()["earnedCount"] == second.json()["earnedCount"]

    async def test_the_list_requires_a_user(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/achievements")).status_code == 401


@pytest.mark.usefixtures("seeded_catalog")
class TestLeaderboard:
    async def test_it_ranks_by_xp(self, authed_client: AsyncClient) -> None:
        await authed_client.post(ENROLL)
        course = await authed_client.get("/api/v1/courses/network-fundamentals")
        lesson_id = course.json()["modules"][0]["lessons"][0]["id"]
        await authed_client.post(f"/api/v1/lessons/{lesson_id}/complete")

        response = await authed_client.get("/api/v1/leaderboard")

        assert response.status_code == 200
        body = response.json()
        assert body["entries"][0]["rank"] == 1
        assert body["entries"][0]["xp"] > 0

    async def test_it_marks_your_own_row(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/leaderboard")

        body = response.json()
        assert body["you"] is not None
        assert body["you"]["isYou"] is True

    async def test_it_never_exposes_an_email(self, authed_client: AsyncClient) -> None:
        """A leaderboard is public within the platform."""
        response = await authed_client.get("/api/v1/leaderboard")
        assert "@" not in response.text

    async def test_the_weekly_board_counts_only_recent_xp(self, authed_client: AsyncClient) -> None:
        await authed_client.post(ENROLL)
        course = await authed_client.get("/api/v1/courses/network-fundamentals")
        lesson_id = course.json()["modules"][0]["lessons"][0]["id"]
        await authed_client.post(f"/api/v1/lessons/{lesson_id}/complete")

        response = await authed_client.get("/api/v1/leaderboard?scope=weekly")

        assert response.status_code == 200
        assert response.json()["entries"][0]["xp"] > 0

    async def test_it_is_readable_without_signing_in(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/leaderboard")
        assert response.status_code == 200
        assert response.json()["you"] is None


@pytest.mark.usefixtures("seeded_catalog")
class TestCertificates:
    @staticmethod
    async def complete_course(client: AsyncClient) -> None:
        await client.post(CERTIFIED_ENROLL)
        course = await client.get(f"/api/v1/courses/{CERTIFIED_SLUG}")
        for module in course.json()["modules"]:
            for lesson in module["lessons"]:
                await client.post(f"/api/v1/lessons/{lesson['id']}/complete")

    async def test_a_certificate_needs_a_finished_course(self, authed_client: AsyncClient) -> None:
        await authed_client.post(CERTIFIED_ENROLL)

        response = await authed_client.post(f"/api/v1/certificates/{CERTIFIED_SLUG}")

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "course_not_completed"

    async def test_finishing_the_course_earns_one(self, authed_client: AsyncClient) -> None:
        await self.complete_course(authed_client)

        response = await authed_client.post(f"/api/v1/certificates/{CERTIFIED_SLUG}")

        assert response.status_code == 200
        body = response.json()
        assert body["serial"].startswith("NLP-")
        assert len(body["verificationCode"]) == 32

    async def test_claiming_twice_returns_the_same_certificate(
        self, authed_client: AsyncClient
    ) -> None:
        await self.complete_course(authed_client)

        first = await authed_client.post(f"/api/v1/certificates/{CERTIFIED_SLUG}")
        second = await authed_client.post(f"/api/v1/certificates/{CERTIFIED_SLUG}")

        assert first.json()["id"] == second.json()["id"]

    async def test_verification_is_public_and_thin(
        self, authed_client: AsyncClient, client: AsyncClient
    ) -> None:
        """The code goes on a CV, so this must work signed out — and must not
        hand out anything the holder did not intend to publish."""
        await self.complete_course(authed_client)
        code = (await authed_client.post(f"/api/v1/certificates/{CERTIFIED_SLUG}")).json()[
            "verificationCode"
        ]

        response = await client.get(f"/api/v1/certificates/verify/{code}")

        assert response.status_code == 200
        body = response.json()
        assert body["valid"] is True
        assert body["recipientName"] == "Test Learner"
        assert "@" not in response.text
        assert "serial" not in body

    async def test_an_unknown_code_is_invalid_not_a_404(self, client: AsyncClient) -> None:
        """Otherwise the status code distinguishes 'wrong' from 'revoked'."""
        response = await client.get("/api/v1/certificates/verify/deadbeef" * 1)

        assert response.status_code == 200
        assert response.json()["valid"] is False

    async def test_revoking_keeps_the_code_resolvable(
        self, authed_client: AsyncClient, client: AsyncClient
    ) -> None:
        await self.complete_course(authed_client)
        certificate = (await authed_client.post(f"/api/v1/certificates/{CERTIFIED_SLUG}")).json()

        # The first registered account is the administrator.
        await authed_client.delete(f"/api/v1/certificates/{certificate['id']}")
        response = await client.get(
            f"/api/v1/certificates/verify/{certificate['verificationCode']}"
        )

        assert response.json()["valid"] is False
        assert response.json()["revoked"] is True
