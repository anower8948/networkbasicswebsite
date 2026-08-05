"""Notes and bookmarks.

Small by design. The only rule worth stating is that **ownership is checked
before existence** everywhere: a note belonging to someone else must 404, not
403, so the endpoint cannot be used to discover which note ids exist.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.progress import Bookmark, Note
from app.models.user import User
from app.repositories.notes import BookmarkRepository, NoteRepository
from app.schemas.notes import (
    BookmarkRead,
    BookmarkWrite,
    NoteRead,
    NoteUpdate,
    NoteWithContext,
    NoteWrite,
)


class NotesService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.notes = NoteRepository(session)
        self.bookmarks = BookmarkRepository(session)

    # ------------------------------------------------------------------ #
    # Notes
    # ------------------------------------------------------------------ #
    async def list_for_lesson(self, user: User, lesson_id: uuid.UUID) -> list[NoteRead]:
        rows = await self.notes.list_for_lesson(user.id, lesson_id)
        return [NoteRead.model_validate(row) for row in rows]

    async def list_all(self, user: User) -> list[NoteWithContext]:
        rows = await self.notes.list_with_context(user.id)
        return [
            NoteWithContext(
                **NoteRead.model_validate(note).model_dump(),
                lesson_title=lesson_title,
                lesson_slug=lesson_slug,
                course_slug=course_slug,
            )
            for note, lesson_title, lesson_slug, course_slug in rows
        ]

    async def create(self, user: User, payload: NoteWrite) -> NoteRead:
        note = Note(
            user_id=user.id,
            lesson_id=payload.lesson_id,
            body=payload.body,
            block_index=payload.block_index,
            is_pinned=payload.is_pinned,
        )
        self.notes.add(note)
        await self.session.commit()
        return NoteRead.model_validate(note)

    async def update(self, user: User, note_id: uuid.UUID, payload: NoteUpdate) -> NoteRead:
        note = await self._own_note(user, note_id)
        if payload.body is not None:
            note.body = payload.body
        if payload.is_pinned is not None:
            note.is_pinned = payload.is_pinned
        await self.session.commit()
        return NoteRead.model_validate(note)

    async def delete(self, user: User, note_id: uuid.UUID) -> None:
        note = await self._own_note(user, note_id)
        await self.notes.delete(note)
        await self.session.commit()

    async def _own_note(self, user: User, note_id: uuid.UUID) -> Note:
        note = await self.notes.get(note_id)
        if note is None or note.user_id != user.id:
            raise NotFoundError("Note not found.")
        return note

    # ------------------------------------------------------------------ #
    # Bookmarks
    # ------------------------------------------------------------------ #
    async def list_bookmarks(self, user: User) -> list[BookmarkRead]:
        rows = await self.bookmarks.list_with_context(user.id)
        return [
            BookmarkRead(
                id=bookmark.id,
                lesson_id=bookmark.lesson_id,
                label=bookmark.label,
                lesson_title=lesson_title,
                lesson_slug=lesson_slug,
                course_slug=course_slug,
                created_at=bookmark.created_at,
            )
            for bookmark, lesson_title, lesson_slug, course_slug in rows
        ]

    async def toggle_bookmark(self, user: User, payload: BookmarkWrite) -> bool:
        """Add or remove — one endpoint, because the UI is one star.

        Returns whether the lesson is bookmarked *after* the call.
        """
        existing = await self.bookmarks.get_for_user_lesson(user.id, payload.lesson_id)
        if existing is not None:
            await self.bookmarks.delete(existing)
            await self.session.commit()
            return False

        self.bookmarks.add(
            Bookmark(user_id=user.id, lesson_id=payload.lesson_id, label=payload.label)
        )
        await self.session.commit()
        return True
