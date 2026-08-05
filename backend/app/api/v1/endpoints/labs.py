"""Hands-on lab endpoints.

The lab library is readable without signing in — the catalogue is marketing as
much as it is navigation — but everything that touches an attempt requires a
user, because an attempt *is* a user's work.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, DbSession, get_optional_user
from app.models.enums import Difficulty, LabKind
from app.models.user import User
from app.schemas.common import ErrorResponse, Page
from app.schemas.lab import (
    HintRequest,
    HintResponse,
    LabAttemptRead,
    LabDetail,
    LabGradeResult,
    LabSummary,
    WorkingTopologyUpdate,
)
from app.services.lab_service import LabService

router = APIRouter(prefix="/labs", tags=["Labs"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

OptionalUser = Annotated[User | None, Depends(get_optional_user)]


@router.get(
    "",
    response_model=Page[LabSummary],
    summary="Browse the lab library",
)
async def list_labs(
    session: DbSession,
    user: OptionalUser,
    kind: LabKind | None = None,
    difficulty: Difficulty | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[LabSummary]:
    """Annotated with the signed-in learner's best score, when there is one."""
    items, total = await LabService(session).list_labs(
        user, kind=kind, difficulty=difficulty, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get(
    "/{slug}",
    response_model=LabDetail,
    responses=_ERRORS,
    summary="One lab's briefing",
)
async def get_lab(slug: str, session: DbSession, user: OptionalUser) -> LabDetail:
    """Requirements and objectives only — never the grading rules or faults."""
    return await LabService(session).get_lab(user, slug)


@router.post(
    "/{slug}/attempts",
    response_model=LabAttemptRead,
    responses=_ERRORS,
    summary="Start or resume an attempt",
)
async def start_attempt(slug: str, session: DbSession, user: CurrentUser) -> LabAttemptRead:
    """Resumes any attempt already in progress, so a refresh keeps the work.

    For a troubleshooting lab this is where faults are applied — server-side, to
    a copy — so the intact network never leaves the server.
    """
    return await LabService(session).start_attempt(user, slug)


@router.put(
    "/attempts/{attempt_id}/topology",
    response_model=LabAttemptRead,
    responses=_ERRORS,
    summary="Autosave the working topology",
)
async def save_topology(
    attempt_id: uuid.UUID,
    payload: WorkingTopologyUpdate,
    session: DbSession,
    user: CurrentUser,
) -> LabAttemptRead:
    return await LabService(session).save_working_topology(user, attempt_id, payload)


@router.post(
    "/attempts/{attempt_id}/check",
    response_model=LabGradeResult,
    responses=_ERRORS,
    summary="Check the work so far without submitting",
)
async def check_attempt(
    attempt_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> LabGradeResult:
    """Free and unlimited: iterating on the feedback *is* the exercise."""
    return await LabService(session).check(user, attempt_id)


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=LabGradeResult,
    responses=_ERRORS,
    summary="Submit the lab for a final grade",
)
async def submit_attempt(
    attempt_id: uuid.UUID, session: DbSession, user: CurrentUser
) -> LabGradeResult:
    """Closes the attempt, awards XP on a first pass, and — once passed —
    reveals what a troubleshooting lab had broken to begin with."""
    return await LabService(session).submit(user, attempt_id)


@router.post(
    "/attempts/{attempt_id}/hint",
    response_model=HintResponse,
    responses=_ERRORS,
    summary="Reveal an objective's hint",
)
async def request_hint(
    attempt_id: uuid.UUID,
    payload: HintRequest,
    session: DbSession,
    user: CurrentUser,
) -> HintResponse:
    return await LabService(session).hint(user, attempt_id, payload.objective_id)
