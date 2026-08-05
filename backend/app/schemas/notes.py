"""Notes and bookmarks — the learner's own annotations."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import Field

from app.schemas.common import APIModel


class NoteWrite(APIModel):
    lesson_id: uuid.UUID
    body: str = Field(min_length=1, max_length=8000)
    # Anchors the note to a content block so it renders beside the passage it
    # is about rather than in an undifferentiated pile at the end.
    block_index: int | None = Field(default=None, ge=0, le=500)
    is_pinned: bool = False


class NoteUpdate(APIModel):
    body: str | None = Field(default=None, min_length=1, max_length=8000)
    is_pinned: bool | None = None


class NoteRead(APIModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    body: str
    block_index: int | None
    is_pinned: bool
    created_at: datetime
    updated_at: datetime


class NoteWithContext(NoteRead):
    """A note on the "all my notes" screen, where the lesson is not implied."""

    lesson_title: str
    lesson_slug: str
    course_slug: str


class BookmarkWrite(APIModel):
    lesson_id: uuid.UUID
    label: str | None = Field(default=None, max_length=120)


class BookmarkRead(APIModel):
    id: uuid.UUID
    lesson_id: uuid.UUID
    label: str | None
    lesson_title: str
    lesson_slug: str
    course_slug: str
    created_at: datetime
