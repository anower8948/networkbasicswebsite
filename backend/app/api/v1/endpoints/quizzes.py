"""Quiz delivery and submission endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUser, DbSession
from app.schemas.common import ErrorResponse
from app.schemas.learning import (
    QuizAttemptSummary,
    QuizForAttempt,
    QuizResult,
    QuizSubmission,
)
from app.services.quiz_service import QuizService

router = APIRouter(prefix="/quizzes", tags=["Quizzes"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
}


@router.post(
    "/{quiz_id}/attempts",
    response_model=QuizForAttempt,
    responses=_ERRORS,
    summary="Start or resume a quiz attempt",
)
async def start_attempt(
    quiz_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> QuizForAttempt:
    """Returns the questions **without** any correctness information.

    Resumes an unsubmitted attempt rather than opening a new one, so a page
    refresh does not consume one of a limited number of attempts.
    """
    return await QuizService(session).start_attempt(user, quiz_id)


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=QuizResult,
    responses=_ERRORS,
    summary="Submit answers and receive the graded result",
)
async def submit_attempt(
    attempt_id: uuid.UUID,
    payload: QuizSubmission,
    session: DbSession,
    user: CurrentUser,
) -> QuizResult:
    """Grading happens here; this is the first response carrying correct answers."""
    return await QuizService(session).submit(user, attempt_id, payload)


@router.get(
    "/{quiz_id}/attempts",
    response_model=list[QuizAttemptSummary],
    responses=_ERRORS,
    summary="This learner's attempt history for a quiz",
)
async def list_attempts(
    quiz_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> list[QuizAttemptSummary]:
    attempts = await QuizService(session).attempts.list_for_user_quiz(user.id, quiz_id)
    return [QuizAttemptSummary.model_validate(attempt) for attempt in attempts]
