"""Lesson viewing and progress endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import CurrentUser, DbSession, get_optional_user
from app.models.user import User
from app.schemas.catalog import LessonDetail
from app.schemas.common import ErrorResponse
from app.schemas.learning import (
    LessonCompletionResult,
    LessonProgressRead,
    LessonProgressUpdate,
)
from app.services.catalog_service import CatalogService
from app.services.learning_service import LearningService

router = APIRouter(prefix="/lessons", tags=["Lessons"])

OptionalUser = Annotated[User | None, Depends(get_optional_user)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get(
    "/{course_slug}/{lesson_slug}",
    response_model=LessonDetail,
    responses=_ERRORS,
    summary="Read a lesson",
)
async def get_lesson(
    course_slug: str,
    lesson_slug: str,
    session: DbSession,
    user: OptionalUser,
) -> LessonDetail:
    """Public, so a lesson can be previewed and linked to.

    Progress fields are populated only for a signed-in learner.
    """
    return await CatalogService(session).get_lesson(course_slug, lesson_slug, user)


@router.put(
    "/{lesson_id}/progress",
    response_model=LessonProgressRead,
    responses=_ERRORS,
    summary="Autosave reading position and study time",
)
async def save_progress(
    lesson_id: uuid.UUID,
    payload: LessonProgressUpdate,
    session: DbSession,
    user: CurrentUser,
) -> LessonProgressRead:
    """Called periodically by the viewer while a lesson is open."""
    record = await LearningService(session).save_position(user, lesson_id, payload)
    return LessonProgressRead.model_validate(record)


@router.post(
    "/{lesson_id}/complete",
    response_model=LessonCompletionResult,
    responses=_ERRORS,
    summary="Mark a lesson complete and award XP",
)
async def complete_lesson(
    lesson_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> LessonCompletionResult:
    """Idempotent: re-completing awards nothing further."""
    return await LearningService(session).complete_lesson(user, lesson_id)
