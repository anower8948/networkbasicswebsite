"""Tests for enrolment, lesson progress, and course completion."""

from __future__ import annotations

from httpx import AsyncClient

COURSE_SLUG = "network-fundamentals"
ENROLL = f"/api/v1/courses/{COURSE_SLUG}/enroll"
COURSE = f"/api/v1/courses/{COURSE_SLUG}"
ENROLLMENTS = "/api/v1/courses/enrollments"
PROGRESS = "/api/v1/users/me/progress"


async def lesson_ids(client: AsyncClient) -> list[str]:
    """Every lesson id in the course, in syllabus order."""
    course = (await client.get(COURSE)).json()
    return [lesson["id"] for module in course["modules"] for lesson in module["lessons"]]


class TestEnrollment:
    async def test_enrolling_creates_an_enrollment(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        response = await authed_client.post(ENROLL)

        assert response.status_code == 201
        assert response.json()["status"] == "active"
        assert response.json()["progressPercent"] == 0.0

    async def test_enrolling_twice_is_idempotent(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        first = await authed_client.post(ENROLL)
        second = await authed_client.post(ENROLL)

        assert second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        assert len((await authed_client.get(ENROLLMENTS)).json()) == 1

    async def test_enrollment_shows_in_the_catalogue(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        course = (await authed_client.get(COURSE)).json()

        assert course["isEnrolled"] is True
        assert course["nextLessonId"] is not None

    async def test_enrolling_requires_authentication(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        assert (await client.post(ENROLL)).status_code == 401

    async def test_enrolling_in_an_unknown_course_is_404(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        response = await authed_client.post("/api/v1/courses/nope/enroll")
        assert response.status_code == 404


class TestLessonProgress:
    async def test_completion_awards_xp(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        response = await authed_client.post(f"/api/v1/lessons/{first}/complete")

        assert response.status_code == 200
        body = response.json()
        assert body["xpAwarded"] == 20
        assert body["status"] == "completed"
        # 20 for the lesson plus 10 for the "First steps" badge it unlocks.
        # `xpAwarded` reports only the lesson's own grant; `totalXp` is the
        # running total *after* the badge was paid, so the two differ here.
        assert body["totalXp"] == 30
        assert [item["slug"] for item in body["newAchievements"]] == ["first-steps"]

    async def test_recompleting_awards_nothing_further(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """The XP ledger's reference deduplication must hold end to end."""
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        await authed_client.post(f"/api/v1/lessons/{first}/complete")
        second = await authed_client.post(f"/api/v1/lessons/{first}/complete")

        assert second.json()["xpAwarded"] == 0
        # 20 for the lesson plus the 10 its badge paid the first time — and no
        # more: the badge must not re-award either.
        assert second.json()["totalXp"] == 30
        assert second.json()["newAchievements"] == []
        # The counter must not double-count either.
        assert (await authed_client.get(PROGRESS)).json()["lessonsCompleted"] == 1

    async def test_completion_advances_course_progress(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        ids = await lesson_ids(authed_client)

        first = await authed_client.post(f"/api/v1/lessons/{ids[0]}/complete")
        assert first.json()["courseProgressPercent"] == 50.0
        assert first.json()["courseCompleted"] is False
        assert first.json()["nextLessonId"] == ids[1]

    async def test_finishing_every_lesson_completes_the_course(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        ids = await lesson_ids(authed_client)

        for lesson_id in ids[:-1]:
            await authed_client.post(f"/api/v1/lessons/{lesson_id}/complete")
        final = await authed_client.post(f"/api/v1/lessons/{ids[-1]}/complete")

        body = final.json()
        assert body["courseCompleted"] is True
        assert body["courseProgressPercent"] == 100.0
        assert body["nextLessonId"] is None
        # 20 for the lesson plus the 100 course bonus.
        assert body["xpAwarded"] == 120

    async def test_course_bonus_is_paid_once(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        ids = await lesson_ids(authed_client)
        for lesson_id in ids:
            await authed_client.post(f"/api/v1/lessons/{lesson_id}/complete")

        total_after_first_pass = (await authed_client.get(PROGRESS)).json()["totalXp"]
        # Re-complete everything; nothing more should be paid.
        for lesson_id in ids:
            await authed_client.post(f"/api/v1/lessons/{lesson_id}/complete")

        assert (await authed_client.get(PROGRESS)).json()["totalXp"] == total_after_first_pass

    async def test_completion_requires_enrollment(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """Progress is only meaningful inside a course the learner joined."""
        first = (await lesson_ids(authed_client))[0]

        response = await authed_client.post(f"/api/v1/lessons/{first}/complete")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "not_enrolled"

    async def test_completion_requires_authentication(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        first = (await lesson_ids(client))[0]
        assert (await client.post(f"/api/v1/lessons/{first}/complete")).status_code == 401

    async def test_lesson_status_appears_in_the_syllabus(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        ids = await lesson_ids(authed_client)
        await authed_client.post(f"/api/v1/lessons/{ids[0]}/complete")

        course = (await authed_client.get(COURSE)).json()
        lessons = course["modules"][0]["lessons"]

        assert lessons[0]["status"] == "completed"
        assert lessons[1]["status"] == "not_started"
        assert course["completedLessonCount"] == 1


class TestReadingPosition:
    async def test_saves_position_and_study_time(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        response = await authed_client.put(
            f"/api/v1/lessons/{first}/progress",
            json={"lastBlockIndex": 4, "timeSpentSeconds": 90},
        )

        assert response.status_code == 200
        assert response.json()["lastBlockIndex"] == 4
        assert response.json()["status"] == "in_progress"

    async def test_position_never_moves_backwards(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """A stale autosave from a scrolled-up tab must not reset progress."""
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        await authed_client.put(
            f"/api/v1/lessons/{first}/progress",
            json={"lastBlockIndex": 8, "timeSpentSeconds": 30},
        )
        response = await authed_client.put(
            f"/api/v1/lessons/{first}/progress",
            json={"lastBlockIndex": 2, "timeSpentSeconds": 10},
        )

        assert response.json()["lastBlockIndex"] == 8

    async def test_study_time_accumulates(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        for _ in range(3):
            await authed_client.put(
                f"/api/v1/lessons/{first}/progress",
                json={"lastBlockIndex": 1, "timeSpentSeconds": 60},
            )

        assert (await authed_client.get(PROGRESS)).json()["totalStudySeconds"] == 180

    async def test_reading_counts_as_activity(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """Working through theory must keep a streak alive."""
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        await authed_client.put(
            f"/api/v1/lessons/{first}/progress",
            json={"lastBlockIndex": 1, "timeSpentSeconds": 60},
        )

        assert (await authed_client.get(PROGRESS)).json()["currentStreakDays"] == 1

    async def test_time_spent_is_capped(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        await authed_client.post(ENROLL)
        first = (await lesson_ids(authed_client))[0]

        response = await authed_client.put(
            f"/api/v1/lessons/{first}/progress",
            json={"lastBlockIndex": 1, "timeSpentSeconds": 999_999},
        )
        assert response.status_code == 422
