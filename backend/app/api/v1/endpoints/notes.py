"""Notes and bookmarks."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import ErrorResponse, MessageResponse
from app.schemas.notes import (
    BookmarkRead,
    BookmarkWrite,
    NoteRead,
    NoteUpdate,
    NoteWithContext,
    NoteWrite,
)
from app.services.notes_service import NotesService

router = APIRouter(tags=["Notes"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get(
    "/notes",
    response_model=list[NoteWithContext],
    responses=_ERRORS,
    summary="Every note this learner has written",
)
async def list_notes(session: DbSession, user: CurrentUser) -> list[NoteWithContext]:
    return await NotesService(session).list_all(user)


@router.get(
    # Deliberately not `/lessons/{lesson_id}/notes`: that collides with the
    # lesson viewer's `/lessons/{course_slug}/{lesson_slug}`, and whichever
    # router was registered first would silently win.
    "/notes/lesson/{lesson_id}",
    response_model=list[NoteRead],
    responses=_ERRORS,
    summary="Notes on one lesson",
)
async def list_lesson_notes(
    lesson_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> list[NoteRead]:
    return await NotesService(session).list_for_lesson(user, lesson_id)


@router.post(
    "/notes",
    response_model=NoteRead,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Write a note",
)
async def create_note(payload: NoteWrite, session: DbSession, user: CurrentUser) -> NoteRead:
    return await NotesService(session).create(user, payload)


@router.patch(
    "/notes/{note_id}",
    response_model=NoteRead,
    responses=_ERRORS,
    summary="Edit or pin a note",
)
async def update_note(
    note_id: uuid.UUID, payload: NoteUpdate, session: DbSession, user: CurrentUser
) -> NoteRead:
    return await NotesService(session).update(user, note_id, payload)


@router.delete(
    "/notes/{note_id}",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Delete a note",
)
async def delete_note(note_id: uuid.UUID, session: DbSession, user: CurrentUser) -> MessageResponse:
    await NotesService(session).delete(user, note_id)
    return MessageResponse(message="Note deleted.")


@router.get(
    "/bookmarks",
    response_model=list[BookmarkRead],
    responses=_ERRORS,
    summary="Saved lessons",
)
async def list_bookmarks(session: DbSession, user: CurrentUser) -> list[BookmarkRead]:
    return await NotesService(session).list_bookmarks(user)


@router.post(
    "/bookmarks",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Bookmark or un-bookmark a lesson",
)
async def toggle_bookmark(
    payload: BookmarkWrite, session: DbSession, user: CurrentUser
) -> MessageResponse:
    """One endpoint for both directions, because the UI is a single star."""
    added = await NotesService(session).toggle_bookmark(user, payload)
    return MessageResponse(message="Bookmarked." if added else "Bookmark removed.")
