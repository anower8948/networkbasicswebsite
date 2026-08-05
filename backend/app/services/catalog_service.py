"""Browsing the course catalogue.

Every read is annotated with the caller's progress when there is one, so the
frontend renders a personalised catalogue from a single request. All the
per-learner lookups are batched — the catalogue page must not issue a query per
course.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.catalog import Course, Lesson, Track
from app.models.enums import ProgressStatus
from app.models.user import User
from app.repositories.catalog import CourseRepository, LessonRepository, TrackRepository
from app.repositories.learning import EnrollmentRepository, LessonProgressRepository
from app.schemas.catalog import (
    CourseDetail,
    CourseSummary,
    LessonDetail,
    LessonNeighbour,
    LessonSummary,
    ModuleSummary,
    TrackSummary,
    TrackWithCourses,
)


class CourseNotFound(NotFoundError):
    code = "course_not_found"
    message = "Course not found."


class LessonNotFound(NotFoundError):
    code = "lesson_not_found"
    message = "Lesson not found."


class CatalogService:
    """Read-side of the learning catalogue."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tracks = TrackRepository(session)
        self.courses = CourseRepository(session)
        self.lessons = LessonRepository(session)
        self.enrollments = EnrollmentRepository(session)
        self.lesson_progress = LessonProgressRepository(session)

    # ------------------------------------------------------------------ #
    # Tracks and courses
    # ------------------------------------------------------------------ #
    async def list_tracks(self, user: User | None) -> list[TrackWithCourses]:
        """The full catalogue: every published track with its courses."""
        tracks = await self.tracks.list_published()
        courses = await self.courses.list_published()

        lesson_counts = await self.courses.lesson_counts([course.id for course in courses])
        enrolled_ids: set[uuid.UUID] = set()
        progress: dict[uuid.UUID, float] = {}
        if user is not None:
            enrolled_ids = await self.enrollments.enrolled_course_ids(user.id)
            progress = await self.enrollments.progress_by_course(user.id)

        by_track: dict[uuid.UUID, list[CourseSummary]] = {}
        for course in courses:
            by_track.setdefault(course.track_id, []).append(
                self._course_summary(course, lesson_counts, enrolled_ids, progress)
            )

        return [
            TrackWithCourses(
                **self._track_summary(track, len(by_track.get(track.id, []))).model_dump(),
                courses=by_track.get(track.id, []),
            )
            for track in tracks
        ]

    async def get_course(self, slug: str, user: User | None) -> CourseDetail:
        """A course's full syllabus, annotated with the learner's progress."""
        course = await self.courses.get_by_slug(slug)
        if course is None or not course.is_published:
            raise CourseNotFound()

        loaded = await self.courses.get_with_syllabus(course.id)
        assert loaded is not None  # just fetched by id

        ordered_lessons = await self.lessons.list_for_course(course.id)
        lesson_ids = [lesson.id for lesson in ordered_lessons]
        quiz_lessons = await self.lessons.quiz_lesson_ids(lesson_ids)

        statuses: dict[uuid.UUID, ProgressStatus] = {}
        is_enrolled = False
        progress_percent = 0.0
        if user is not None:
            statuses = await self.lesson_progress.status_by_lesson(user.id, lesson_ids)
            enrollment = await self.enrollments.get_for_user_course(user.id, course.id)
            if enrollment is not None:
                is_enrolled = True
                progress_percent = enrollment.progress_percent

        modules = [
            ModuleSummary(
                id=module.id,
                slug=module.slug,
                title=module.title,
                description=module.description,
                order_index=module.order_index,
                lessons=[
                    self._lesson_summary(lesson, quiz_lessons, statuses, include_status=user)
                    for lesson in sorted(module.lessons, key=lambda item: item.order_index)
                    if lesson.is_published
                ],
            )
            for module in sorted(loaded.modules, key=lambda item: item.order_index)
        ]

        completed = sum(1 for status in statuses.values() if status is ProgressStatus.COMPLETED)
        # "Continue" targets the first lesson the learner has not finished.
        next_lesson_id = next(
            (
                lesson.id
                for lesson in ordered_lessons
                if statuses.get(lesson.id) is not ProgressStatus.COMPLETED
            ),
            None,
        )

        return CourseDetail(
            id=course.id,
            track_id=course.track_id,
            slug=course.slug,
            title=course.title,
            summary=course.summary,
            description=course.description,
            difficulty=course.difficulty,
            estimated_minutes=course.estimated_minutes,
            cover_image_url=course.cover_image_url,
            tags=course.tags,
            prerequisites=course.prerequisites,
            grants_certificate=course.grants_certificate,
            modules=modules,
            lesson_count=len(ordered_lessons),
            is_enrolled=is_enrolled,
            progress_percent=progress_percent,
            completed_lesson_count=completed,
            next_lesson_id=next_lesson_id,
        )

    # ------------------------------------------------------------------ #
    # Lessons
    # ------------------------------------------------------------------ #
    async def get_lesson(
        self, course_slug: str, lesson_slug: str, user: User | None
    ) -> LessonDetail:
        """One lesson with its body, navigation, and the learner's position."""
        lesson = await self.lessons.get_by_slug(course_slug, lesson_slug)
        if lesson is None or not lesson.is_published:
            raise LessonNotFound()

        module = lesson.module
        course = module.course

        # Neighbours come from the same ordering the syllabus renders, so
        # "next" always matches what the learner sees in the sidebar.
        ordered = await self.lessons.list_for_course(course.id)
        position = next((index for index, item in enumerate(ordered) if item.id == lesson.id), None)
        previous_lesson = (
            self._neighbour(ordered[position - 1]) if position not in (None, 0) else None
        )
        next_lesson = (
            self._neighbour(ordered[position + 1])
            if position is not None and position + 1 < len(ordered)
            else None
        )

        status = ProgressStatus.NOT_STARTED
        last_block_index = 0
        if user is not None:
            record = await self.lesson_progress.get_for_user_lesson(user.id, lesson.id)
            if record is not None:
                status = record.status
                last_block_index = record.last_block_index

        return LessonDetail(
            id=lesson.id,
            module_id=module.id,
            course_id=course.id,
            course_slug=course.slug,
            course_title=course.title,
            module_title=module.title,
            slug=lesson.slug,
            title=lesson.title,
            summary=lesson.summary,
            lesson_type=lesson.lesson_type,
            objectives=lesson.objectives,
            content_blocks=lesson.content_blocks,
            estimated_minutes=lesson.estimated_minutes,
            xp_reward=lesson.xp_reward,
            order_index=lesson.order_index,
            has_quiz=lesson.quiz is not None,
            quiz_id=lesson.quiz.id if lesson.quiz else None,
            status=status,
            last_block_index=last_block_index,
            previous_lesson=previous_lesson,
            next_lesson=next_lesson,
        )

    # ------------------------------------------------------------------ #
    # Projection helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _track_summary(track: Track, course_count: int) -> TrackSummary:
        return TrackSummary(
            id=track.id,
            slug=track.slug,
            title=track.title,
            description=track.description,
            level=track.level,
            icon=track.icon,
            accent_color=track.accent_color,
            order_index=track.order_index,
            course_count=course_count,
        )

    @staticmethod
    def course_summary_for(
        course: Course,
        *,
        lesson_count: int = 0,
        is_enrolled: bool = False,
        progress_percent: float | None = None,
    ) -> CourseSummary:
        """Project one course. Shared with the enrolments endpoint."""
        return CourseSummary(
            id=course.id,
            track_id=course.track_id,
            slug=course.slug,
            title=course.title,
            summary=course.summary,
            difficulty=course.difficulty,
            estimated_minutes=course.estimated_minutes,
            cover_image_url=course.cover_image_url,
            tags=course.tags,
            order_index=course.order_index,
            lesson_count=lesson_count,
            grants_certificate=course.grants_certificate,
            is_enrolled=is_enrolled,
            progress_percent=progress_percent if is_enrolled else None,
        )

    @staticmethod
    def _course_summary(
        course: Course,
        lesson_counts: dict[uuid.UUID, int],
        enrolled_ids: set[uuid.UUID],
        progress: dict[uuid.UUID, float],
    ) -> CourseSummary:
        is_enrolled = course.id in enrolled_ids
        return CourseSummary(
            id=course.id,
            track_id=course.track_id,
            slug=course.slug,
            title=course.title,
            summary=course.summary,
            difficulty=course.difficulty,
            estimated_minutes=course.estimated_minutes,
            cover_image_url=course.cover_image_url,
            tags=course.tags,
            order_index=course.order_index,
            lesson_count=lesson_counts.get(course.id, 0),
            grants_certificate=course.grants_certificate,
            is_enrolled=is_enrolled,
            progress_percent=progress.get(course.id) if is_enrolled else None,
        )

    @staticmethod
    def _lesson_summary(
        lesson: Lesson,
        quiz_lessons: set[uuid.UUID],
        statuses: dict[uuid.UUID, ProgressStatus],
        *,
        include_status: User | None,
    ) -> LessonSummary:
        return LessonSummary(
            id=lesson.id,
            slug=lesson.slug,
            title=lesson.title,
            summary=lesson.summary,
            lesson_type=lesson.lesson_type,
            estimated_minutes=lesson.estimated_minutes,
            xp_reward=lesson.xp_reward,
            order_index=lesson.order_index,
            has_quiz=lesson.id in quiz_lessons,
            status=(
                statuses.get(lesson.id, ProgressStatus.NOT_STARTED)
                if include_status is not None
                else None
            ),
        )

    @staticmethod
    def _neighbour(lesson: Lesson) -> LessonNeighbour:
        return LessonNeighbour(id=lesson.id, slug=lesson.slug, title=lesson.title)
