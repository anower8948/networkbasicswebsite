"""Queries over a learner's notes and bookmarks."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Row, select

from app.models.catalog import Course, Lesson, Module
from app.models.progress import Bookmark, Note
from app.repositories.base import BaseRepository


class NoteRepository(BaseRepository[Note]):
    model = Note

    async def list_for_lesson(self, user_id: uuid.UUID, lesson_id: uuid.UUID) -> Sequence[Note]:
        result = await self.session.execute(
            select(Note)
            .where(Note.user_id == user_id, Note.lesson_id == lesson_id)
            # Pinned first, then by where in the lesson they sit — which is the
            # order they make sense read in.
            .order_by(Note.is_pinned.desc(), Note.block_index, Note.created_at)
        )
        return result.scalars().all()

    async def list_with_context(
        self, user_id: uuid.UUID, limit: int = 100
    ) -> Sequence[Row[tuple[Note, str, str, str]]]:
        """Every note plus enough of its lesson to link back to it.

        One join rather than a lookup per note: the notes page is otherwise the
        classic N+1.
        """
        result = await self.session.execute(
            select(Note, Lesson.title, Lesson.slug, Course.slug)
            .join(Lesson, Lesson.id == Note.lesson_id)
            .join(Module, Module.id == Lesson.module_id)
            .join(Course, Course.id == Module.course_id)
            .where(Note.user_id == user_id)
            .order_by(Note.is_pinned.desc(), Note.updated_at.desc())
            .limit(limit)
        )
        return result.all()


class BookmarkRepository(BaseRepository[Bookmark]):
    model = Bookmark

    async def get_for_user_lesson(
        self, user_id: uuid.UUID, lesson_id: uuid.UUID
    ) -> Bookmark | None:
        result = await self.session.execute(
            select(Bookmark).where(Bookmark.user_id == user_id, Bookmark.lesson_id == lesson_id)
        )
        return result.scalar_one_or_none()

    async def list_with_context(
        self, user_id: uuid.UUID
    ) -> Sequence[Row[tuple[Bookmark, str, str, str]]]:
        result = await self.session.execute(
            select(Bookmark, Lesson.title, Lesson.slug, Course.slug)
            .join(Lesson, Lesson.id == Bookmark.lesson_id)
            .join(Module, Module.id == Lesson.module_id)
            .join(Course, Course.id == Module.course_id)
            .where(Bookmark.user_id == user_id)
            .order_by(Bookmark.created_at.desc())
        )
        return result.all()
