"""Queries over tracks, courses, modules, and lessons."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.catalog import Course, Lesson, Module, Quiz, Track
from app.repositories.base import BaseRepository


class TrackRepository(BaseRepository[Track]):
    model = Track

    async def list_published(self) -> Sequence[Track]:
        result = await self.session.execute(
            select(Track).where(Track.is_published.is_(True)).order_by(Track.order_index)
        )
        return result.scalars().all()

    async def get_by_slug(self, slug: str) -> Track | None:
        result = await self.session.execute(select(Track).where(Track.slug == slug))
        return result.scalar_one_or_none()


class CourseRepository(BaseRepository[Course]):
    model = Course

    async def list_published(self, *, track_id: uuid.UUID | None = None) -> Sequence[Course]:
        stmt = select(Course).where(Course.is_published.is_(True))
        if track_id is not None:
            stmt = stmt.where(Course.track_id == track_id)
        result = await self.session.execute(stmt.order_by(Course.order_index))
        return result.scalars().all()

    async def get_by_slug(self, slug: str) -> Course | None:
        result = await self.session.execute(select(Course).where(Course.slug == slug))
        return result.scalar_one_or_none()

    async def get_with_syllabus(self, course_id: uuid.UUID) -> Course | None:
        """Load a course with its modules and lesson headers.

        `selectinload` issues one extra query per level rather than a joined
        load; a join would multiply the course row by every lesson and ship the
        same course columns hundreds of times.
        """
        result = await self.session.execute(
            select(Course)
            .options(selectinload(Course.modules).selectinload(Module.lessons))
            .where(Course.id == course_id)
        )
        return result.scalar_one_or_none()

    async def lesson_counts(self, course_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Published lesson count per course, in one query.

        Counting per course in a loop is the N+1 that would otherwise show up
        on the catalogue page.
        """
        if not course_ids:
            return {}
        result = await self.session.execute(
            select(Module.course_id, func.count(Lesson.id))
            .join(Lesson, Lesson.module_id == Module.id)
            .where(Module.course_id.in_(course_ids), Lesson.is_published.is_(True))
            .group_by(Module.course_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}


class LessonRepository(BaseRepository[Lesson]):
    model = Lesson

    async def get_with_context(self, lesson_id: uuid.UUID) -> Lesson | None:
        """Load a lesson together with its module, course, and quiz."""
        result = await self.session.execute(
            select(Lesson)
            .options(
                selectinload(Lesson.module).selectinload(Module.course),
                selectinload(Lesson.quiz),
            )
            .where(Lesson.id == lesson_id)
        )
        return result.scalar_one_or_none()

    async def get_by_slug(self, course_slug: str, lesson_slug: str) -> Lesson | None:
        result = await self.session.execute(
            select(Lesson)
            .join(Module, Lesson.module_id == Module.id)
            .join(Course, Module.course_id == Course.id)
            .options(
                selectinload(Lesson.module).selectinload(Module.course),
                selectinload(Lesson.quiz),
            )
            .where(Course.slug == course_slug, Lesson.slug == lesson_slug)
        )
        return result.scalar_one_or_none()

    async def list_for_course(self, course_id: uuid.UUID) -> Sequence[Lesson]:
        """Every published lesson in a course, in syllabus order.

        The ordering must match what the learner sees, since "next lesson" and
        course completion percentage are both derived from this sequence.
        """
        result = await self.session.execute(
            select(Lesson)
            .join(Module, Lesson.module_id == Module.id)
            .where(Module.course_id == course_id, Lesson.is_published.is_(True))
            .order_by(Module.order_index, Lesson.order_index)
        )
        return result.scalars().all()

    async def count_for_course(self, course_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(Lesson.id))
            .join(Module, Lesson.module_id == Module.id)
            .where(Module.course_id == course_id, Lesson.is_published.is_(True))
        )
        return int(result.scalar_one())

    async def quiz_lesson_ids(self, lesson_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Which of these lessons have a quiz — one query, not one per lesson."""
        if not lesson_ids:
            return set()
        result = await self.session.execute(
            select(Quiz.lesson_id).where(Quiz.lesson_id.in_(lesson_ids))
        )
        return {row[0] for row in result.all()}
