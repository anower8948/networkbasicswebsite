"""Queries over enrolments, lesson progress, and quiz attempts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.catalog import Quiz, QuizQuestion
from app.models.enums import ProgressStatus
from app.models.progress import Enrollment, LessonProgress, QuizAttempt
from app.repositories.base import BaseRepository


class EnrollmentRepository(BaseRepository[Enrollment]):
    model = Enrollment

    async def get_for_user_course(
        self, user_id: uuid.UUID, course_id: uuid.UUID
    ) -> Enrollment | None:
        result = await self.session.execute(
            select(Enrollment).where(
                Enrollment.user_id == user_id, Enrollment.course_id == course_id
            )
        )
        return result.scalar_one_or_none()

    async def list_for_user(self, user_id: uuid.UUID) -> Sequence[Enrollment]:
        result = await self.session.execute(
            select(Enrollment)
            .options(selectinload(Enrollment.course))
            .where(Enrollment.user_id == user_id)
            .order_by(Enrollment.updated_at.desc())
        )
        return result.scalars().all()

    async def enrolled_course_ids(self, user_id: uuid.UUID) -> set[uuid.UUID]:
        """Used to annotate the catalogue without a query per course."""
        result = await self.session.execute(
            select(Enrollment.course_id).where(Enrollment.user_id == user_id)
        )
        return {row[0] for row in result.all()}

    async def progress_by_course(self, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
        result = await self.session.execute(
            select(Enrollment.course_id, Enrollment.progress_percent).where(
                Enrollment.user_id == user_id
            )
        )
        return {row[0]: float(row[1]) for row in result.all()}


class LessonProgressRepository(BaseRepository[LessonProgress]):
    model = LessonProgress

    async def get_for_user_lesson(
        self, user_id: uuid.UUID, lesson_id: uuid.UUID
    ) -> LessonProgress | None:
        result = await self.session.execute(
            select(LessonProgress).where(
                LessonProgress.user_id == user_id, LessonProgress.lesson_id == lesson_id
            )
        )
        return result.scalar_one_or_none()

    async def status_by_lesson(
        self, user_id: uuid.UUID, lesson_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, ProgressStatus]:
        """Status for a batch of lessons — one query for a whole syllabus."""
        if not lesson_ids:
            return {}
        result = await self.session.execute(
            select(LessonProgress.lesson_id, LessonProgress.status).where(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id.in_(lesson_ids),
            )
        )
        return {row[0]: row[1] for row in result.all()}

    async def completed_lesson_ids(
        self, user_id: uuid.UUID, lesson_ids: Sequence[uuid.UUID]
    ) -> set[uuid.UUID]:
        if not lesson_ids:
            return set()
        result = await self.session.execute(
            select(LessonProgress.lesson_id).where(
                LessonProgress.user_id == user_id,
                LessonProgress.lesson_id.in_(lesson_ids),
                LessonProgress.status == ProgressStatus.COMPLETED,
            )
        )
        return {row[0] for row in result.all()}


class QuizRepository(BaseRepository[Quiz]):
    model = Quiz

    async def get_with_questions(self, quiz_id: uuid.UUID) -> Quiz | None:
        """Load a quiz with its questions and their options."""
        result = await self.session.execute(
            select(Quiz)
            .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
            .where(Quiz.id == quiz_id)
        )
        return result.scalar_one_or_none()

    async def get_for_lesson(self, lesson_id: uuid.UUID) -> Quiz | None:
        result = await self.session.execute(
            select(Quiz)
            .options(selectinload(Quiz.questions).selectinload(QuizQuestion.options))
            .where(Quiz.lesson_id == lesson_id)
        )
        return result.scalar_one_or_none()


class QuizAttemptRepository(BaseRepository[QuizAttempt]):
    model = QuizAttempt

    async def list_for_user_quiz(
        self, user_id: uuid.UUID, quiz_id: uuid.UUID
    ) -> Sequence[QuizAttempt]:
        result = await self.session.execute(
            select(QuizAttempt)
            .where(QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == quiz_id)
            .order_by(QuizAttempt.attempt_number.desc())
        )
        return result.scalars().all()

    async def count_for_user_quiz(self, user_id: uuid.UUID, quiz_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(QuizAttempt.id)).where(
                QuizAttempt.user_id == user_id, QuizAttempt.quiz_id == quiz_id
            )
        )
        return int(result.scalar_one())

    async def get_open_attempt(self, user_id: uuid.UUID, quiz_id: uuid.UUID) -> QuizAttempt | None:
        """An attempt started but not yet submitted.

        Reusing it means a refreshed page resumes rather than burning another
        attempt against `max_attempts`.
        """
        from app.models.enums import AttemptStatus

        result = await self.session.execute(
            select(QuizAttempt)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .order_by(QuizAttempt.attempt_number.desc())
        )
        return result.scalars().first()

    async def has_passed(self, user_id: uuid.UUID, quiz_id: uuid.UUID) -> bool:
        """Whether this quiz was already passed — gates repeat XP awards."""
        from app.models.enums import AttemptStatus

        result = await self.session.execute(
            select(QuizAttempt.id)
            .where(
                QuizAttempt.user_id == user_id,
                QuizAttempt.quiz_id == quiz_id,
                QuizAttempt.status == AttemptStatus.PASSED,
            )
            .limit(1)
        )
        return result.first() is not None
