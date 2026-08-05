"""Tests for catalogue browsing and the seeded content itself."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

TRACKS = "/api/v1/courses/tracks"
COURSE = "/api/v1/courses/network-fundamentals"
LESSON = "/api/v1/lessons/network-fundamentals/osi-model"


class TestCatalogBrowsing:
    async def test_lists_published_tracks_with_courses(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        response = await client.get(TRACKS)

        assert response.status_code == 200
        tracks = response.json()
        # Only the Foundations track is published; the other two are roadmap.
        assert [track["slug"] for track in tracks] == ["foundations"]
        assert len(tracks[0]["courses"]) == 2

    async def test_catalogue_is_public(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """Browsing must not require an account."""
        assert (await client.get(TRACKS)).status_code == 200
        assert (await client.get(COURSE)).status_code == 200

    async def test_anonymous_browsing_omits_progress(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        course = (await client.get(COURSE)).json()

        assert course["isEnrolled"] is False
        assert course["progressPercent"] == 0.0
        # Lesson status is meaningless without a learner.
        assert course["modules"][0]["lessons"][0]["status"] is None

    async def test_course_carries_its_syllabus(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        course = (await client.get(COURSE)).json()

        assert course["title"] == "Network Fundamentals"
        assert course["lessonCount"] == 2
        lessons = course["modules"][0]["lessons"]
        assert [lesson["slug"] for lesson in lessons] == ["osi-model", "tcp-ip-model"]
        assert lessons[0]["hasQuiz"] is True

    async def test_syllabus_omits_lesson_bodies(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """A table of contents must not ship every lesson's prose."""
        lesson = (await client.get(COURSE)).json()["modules"][0]["lessons"][0]
        assert "contentBlocks" not in lesson

    async def test_unknown_course_is_404(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        response = await client.get("/api/v1/courses/does-not-exist")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "course_not_found"


class TestLessonViewing:
    async def test_returns_the_lesson_body(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        response = await client.get(LESSON)

        assert response.status_code == 200
        lesson = response.json()
        assert lesson["title"] == "The OSI Model"
        assert len(lesson["contentBlocks"]) > 5
        assert lesson["objectives"]

    async def test_includes_navigation_context(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        lesson = (await client.get(LESSON)).json()

        assert lesson["courseTitle"] == "Network Fundamentals"
        assert lesson["previousLesson"] is None  # first in the course
        assert lesson["nextLesson"]["slug"] == "tcp-ip-model"

    async def test_last_lesson_has_no_next(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        lesson = (await client.get("/api/v1/lessons/network-fundamentals/tcp-ip-model")).json()

        assert lesson["previousLesson"]["slug"] == "osi-model"
        assert lesson["nextLesson"] is None

    async def test_reports_an_attached_quiz(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        lesson = (await client.get(LESSON)).json()

        assert lesson["hasQuiz"] is True
        assert lesson["quizId"] is not None

    async def test_unknown_lesson_is_404(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        response = await client.get("/api/v1/lessons/network-fundamentals/nope")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "lesson_not_found"


class TestSeededContent:
    """The authored content is a shipped artefact — validate it like one."""

    async def test_every_block_passes_validation(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """The seeder validates on write; this confirms what is stored round-trips."""
        from app.schemas.content import validate_blocks

        for course_slug, lesson_slug in [
            ("network-fundamentals", "osi-model"),
            ("network-fundamentals", "tcp-ip-model"),
            ("ipv4-addressing-subnetting", "ipv4-addressing"),
            ("ipv4-addressing-subnetting", "subnetting"),
        ]:
            lesson = (await client.get(f"/api/v1/lessons/{course_slug}/{lesson_slug}")).json()
            validate_blocks(lesson["contentBlocks"])

    async def test_every_lesson_declares_objectives(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        for course_slug, lesson_slug in [
            ("network-fundamentals", "osi-model"),
            ("ipv4-addressing-subnetting", "subnetting"),
        ]:
            lesson = (await client.get(f"/api/v1/lessons/{course_slug}/{lesson_slug}")).json()
            assert lesson["objectives"], f"{lesson_slug} has no learning objectives"

    async def test_choice_questions_have_exactly_the_right_correct_count(
        self, session: Any, seeded_catalog: dict[str, int]
    ) -> None:
        """A single-choice question with two correct options is ungradeable."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models.catalog import QuizQuestion
        from app.models.enums import QuestionType

        result = await session.execute(
            select(QuizQuestion).options(selectinload(QuizQuestion.options))
        )
        questions = result.scalars().all()
        assert questions, "seed produced no questions"

        for question in questions:
            correct = [option for option in question.options if option.is_correct]

            if question.question_type in (
                QuestionType.SINGLE_CHOICE,
                QuestionType.TRUE_FALSE,
            ):
                assert len(correct) == 1, f"{question.prompt!r} needs exactly one correct option"
            elif question.question_type is QuestionType.MULTIPLE_CHOICE:
                assert len(correct) >= 1, f"{question.prompt!r} has no correct option"

    async def test_text_questions_carry_an_answer_key(
        self, session: Any, seeded_catalog: dict[str, int]
    ) -> None:
        """Without a key these can never be answered correctly."""
        from sqlalchemy import select

        from app.models.catalog import QuizQuestion
        from app.models.enums import QuestionType

        text_types = {
            QuestionType.FILL_BLANK,
            QuestionType.SUBNET_CALC,
            QuestionType.CLI_COMMAND,
            QuestionType.ORDERING,
            QuestionType.MATCHING,
        }
        result = await session.execute(
            select(QuizQuestion).where(QuizQuestion.question_type.in_(text_types))
        )
        for question in result.scalars().all():
            assert question.answer_key, f"{question.prompt!r} has no answer key"
