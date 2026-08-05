"""Enrolment and lesson progress.

This is where the catalogue meets the progress engine: completing a lesson
records progress, awards XP through :class:`ProgressService` (which handles
deduplication), recomputes the course percentage, and — when the last lesson
lands — completes the course and pays the course bonus.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.catalog import Course, Lesson
from app.models.enums import EnrollmentStatus, ProgressStatus, XPReason
from app.models.progress import Enrollment, LessonProgress
from app.models.user import User
from app.repositories.catalog import CourseRepository, LessonRepository
from app.repositories.learning import EnrollmentRepository, LessonProgressRepository
from app.schemas.learning import (
    LessonCompletionResult,
    LessonProgressUpdate,
)
from app.services.achievement_service import award_new_achievements
from app.services.progress_service import ProgressService, XPGrant

logger = get_logger(__name__)

# Bonus paid once, when the final lesson of a course is completed.
COURSE_COMPLETION_XP = 100


class NotEnrolled(ConflictError):
    status_code = 403
    code = "not_enrolled"
    message = "Enrol in this course before tracking progress."


class LearningService:
    """Write-side of the learning experience."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.courses = CourseRepository(session)
        self.lessons = LessonRepository(session)
        self.enrollments = EnrollmentRepository(session)
        self.lesson_progress = LessonProgressRepository(session)
        self.progress = ProgressService(session)

    # ------------------------------------------------------------------ #
    # Enrolment
    # ------------------------------------------------------------------ #
    async def enroll(self, user: User, course_slug: str) -> Enrollment:
        """Enrol in a course. Idempotent — re-enrolling returns the existing row."""
        course = await self.courses.get_by_slug(course_slug)
        if course is None or not course.is_published:
            raise NotFoundError("Course not found.")

        existing = await self.enrollments.get_for_user_course(user.id, course.id)
        if existing is not None:
            # Re-enrolling after dropping out resumes rather than erroring.
            if existing.status is EnrollmentStatus.DROPPED:
                existing.status = EnrollmentStatus.ACTIVE
                await self.session.commit()
            return existing

        enrollment = Enrollment(
            user_id=user.id,
            course_id=course.id,
            status=EnrollmentStatus.ACTIVE,
            started_at=utcnow(),
        )
        self.enrollments.add(enrollment)
        try:
            await self.session.commit()
        except IntegrityError:
            # Two concurrent enrolments; the unique index is the arbiter.
            await self.session.rollback()
            existing = await self.enrollments.get_for_user_course(user.id, course.id)
            if existing is None:
                raise
            return existing

        logger.info(
            "Learner enrolled",
            extra={"user_id": str(user.id), "course": course.slug},
        )
        return enrollment

    async def list_enrollments(self, user: User) -> Sequence[Enrollment]:
        return await self.enrollments.list_for_user(user.id)

    # ------------------------------------------------------------------ #
    # Lesson progress
    # ------------------------------------------------------------------ #
    async def _require_lesson(self, lesson_id: uuid.UUID) -> tuple[Lesson, Course]:
        lesson = await self.lessons.get_with_context(lesson_id)
        if lesson is None or not lesson.is_published:
            raise NotFoundError("Lesson not found.")
        return lesson, lesson.module.course

    async def _get_or_create_progress(self, user: User, lesson_id: uuid.UUID) -> LessonProgress:
        record = await self.lesson_progress.get_for_user_lesson(user.id, lesson_id)
        if record is None:
            record = LessonProgress(
                user_id=user.id,
                lesson_id=lesson_id,
                status=ProgressStatus.IN_PROGRESS,
            )
            self.lesson_progress.add(record)
            await self.session.flush()
        return record

    async def save_position(
        self, user: User, lesson_id: uuid.UUID, payload: LessonProgressUpdate
    ) -> LessonProgress:
        """Autosave the reading position and accumulate time spent.

        Also advances the study streak, so simply reading counts as activity —
        a learner working through theory should not lose their streak for not
        finishing a lesson that day.
        """
        lesson, course = await self._require_lesson(lesson_id)
        await self._require_enrollment(user, course)

        record = await self._get_or_create_progress(user, lesson.id)
        # Never move the marker backwards: a stale autosave from a scrolled-up
        # tab would otherwise reset a further-along position.
        record.last_block_index = max(record.last_block_index, payload.last_block_index)
        record.time_spent_seconds += payload.time_spent_seconds
        if record.status is ProgressStatus.NOT_STARTED:
            record.status = ProgressStatus.IN_PROGRESS

        if payload.time_spent_seconds > 0:
            await self.progress.record_activity(
                user, study_seconds=payload.time_spent_seconds, commit=False
            )

        await self.session.commit()
        return record

    async def complete_lesson(self, user: User, lesson_id: uuid.UUID) -> LessonCompletionResult:
        """Mark a lesson complete, award XP, and roll up course progress."""
        lesson, course = await self._require_lesson(lesson_id)
        enrollment = await self._require_enrollment(user, course)

        record = await self._get_or_create_progress(user, lesson.id)
        already_complete = record.status is ProgressStatus.COMPLETED

        if not already_complete:
            record.status = ProgressStatus.COMPLETED
            record.completed_at = utcnow()

        # Idempotent by construction: the grant carries the lesson reference, so
        # re-completing pays nothing even though this runs every time.
        grant = await self.progress.grant_xp(
            user,
            lesson.xp_reward,
            XPReason.LESSON_COMPLETED,
            reference_type="lesson",
            reference_id=lesson.id,
            commit=False,
        )

        if not already_complete:
            stats = await self.progress.stats_for(user)
            stats.lessons_completed += 1

        percent, completed_count, total = await self._recompute_course_progress(
            user, course, enrollment
        )

        course_completed = False
        if total > 0 and completed_count >= total and enrollment.completed_at is None:
            enrollment.status = EnrollmentStatus.COMPLETED
            enrollment.completed_at = utcnow()
            course_completed = True

            course_grant = await self.progress.grant_xp(
                user,
                COURSE_COMPLETION_XP,
                XPReason.COURSE_COMPLETED,
                reference_type="course",
                reference_id=course.id,
                commit=False,
            )
            stats = await self.progress.stats_for(user)
            stats.courses_completed += 1
            # Report the combined award, so the UI shows the full amount
            # earned rather than only the lesson's share.
            grant = XPGrant(
                awarded=grant.awarded + course_grant.awarded,
                total_xp=course_grant.total_xp,
                level=course_grant.level,
                leveled_up=grant.leveled_up or course_grant.leveled_up,
                was_duplicate=grant.was_duplicate and course_grant.was_duplicate,
            )
            logger.info(
                "Course completed",
                extra={"user_id": str(user.id), "course": course.slug},
            )

        await self.progress.record_activity(user, commit=False)
        await self.session.commit()

        # Evaluated after the commit, never inside `grant_xp`: badges award XP
        # themselves, so calling this from the grant path would recurse.
        new_achievements = await award_new_achievements(self.session, user)

        total_xp, level, leveled_up = grant.total_xp, grant.level, grant.leveled_up
        if new_achievements:
            # A badge pays XP of its own *after* the grant above computed its
            # totals. Re-reading keeps the number the UI shows consistent with
            # the badge it is celebrating in the same response.
            stats = await self.progress.stats_for(user)
            leveled_up = leveled_up or stats.level > level
            total_xp, level = stats.total_xp, stats.level

        next_lesson_id = await self._next_incomplete_lesson(user, course.id)

        return LessonCompletionResult(
            lesson_id=lesson.id,
            status=ProgressStatus.COMPLETED,
            xp_awarded=grant.awarded,
            total_xp=total_xp,
            level=level,
            leveled_up=leveled_up,
            course_progress_percent=percent,
            course_completed=course_completed,
            next_lesson_id=next_lesson_id,
            new_achievements=new_achievements,
        )

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _require_enrollment(self, user: User, course: Course) -> Enrollment:
        enrollment = await self.enrollments.get_for_user_course(user.id, course.id)
        if enrollment is None:
            raise NotEnrolled()
        return enrollment

    async def _recompute_course_progress(
        self, user: User, course: Course, enrollment: Enrollment
    ) -> tuple[float, int, int]:
        """Recalculate the cached completion percentage from lesson progress.

        Derived on every completion rather than incremented, so unpublishing a
        lesson or adding one cannot leave the percentage permanently wrong.
        """
        lesson_ids = [lesson.id for lesson in await self.lessons.list_for_course(course.id)]
        total = len(lesson_ids)
        completed = len(await self.lesson_progress.completed_lesson_ids(user.id, lesson_ids))

        percent = round((completed / total) * 100, 1) if total else 0.0
        enrollment.progress_percent = percent
        return percent, completed, total

    async def _next_incomplete_lesson(self, user: User, course_id: uuid.UUID) -> uuid.UUID | None:
        ordered = await self.lessons.list_for_course(course_id)
        lesson_ids = [lesson.id for lesson in ordered]
        completed = await self.lesson_progress.completed_lesson_ids(user.id, lesson_ids)
        return next((item for item in lesson_ids if item not in completed), None)
