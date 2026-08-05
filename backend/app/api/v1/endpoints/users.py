"""User profile and progress endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentAdmin, CurrentUser, DbSession, UserServiceDep
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.common import ErrorResponse, MessageResponse, Page
from app.schemas.progress import ActivityPing, ProgressSummary
from app.schemas.user import UserPublic, UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.get("/me", response_model=UserRead, responses=_ERRORS, summary="Current user profile")
async def read_me(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.patch(
    "/me",
    response_model=UserRead,
    responses=_ERRORS,
    summary="Update the current user's profile",
)
async def update_me(
    payload: UserUpdate,
    user: CurrentUser,
    service: UserServiceDep,
) -> UserRead:
    updated = await service.update_profile(user, payload)
    return UserRead.model_validate(updated)


@router.get(
    "/me/progress",
    response_model=ProgressSummary,
    responses=_ERRORS,
    summary="Progress summary for the dashboard",
)
async def read_my_progress(user: CurrentUser, service: UserServiceDep) -> ProgressSummary:
    """XP, level, streaks, counters and a short activity feed in one call."""
    return await service.progress_summary(user)


@router.post(
    "/me/activity",
    response_model=ProgressSummary,
    responses=_ERRORS,
    summary="Record study activity and advance the streak",
)
async def record_activity(
    payload: ActivityPing,
    user: CurrentUser,
    service: UserServiceDep,
) -> ProgressSummary:
    """Called periodically by the client while a lesson is open.

    Returns the refreshed summary so a streak increment or level-up appears
    without a follow-up request.
    """
    await service.progress.record_activity(user, study_seconds=payload.study_seconds)
    return await service.progress_summary(user)


@router.post(
    "/me/deactivate",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Deactivate the current account",
)
async def deactivate_me(user: CurrentUser, service: UserServiceDep) -> MessageResponse:
    """Soft deactivation — learning history and certificates are preserved."""
    await service.deactivate(user)
    return MessageResponse(message="Your account has been deactivated.")


@router.get(
    "/{user_id}",
    response_model=UserPublic,
    responses=_ERRORS,
    summary="Public profile of any user",
)
async def read_user(user_id: uuid.UUID, service: UserServiceDep, _: CurrentUser) -> UserPublic:
    """Returns only publicly shareable fields, never email or account state."""
    profile = await service.get_profile(user_id)
    return UserPublic.model_validate(profile)


@router.get(
    "",
    response_model=Page[UserRead],
    responses=_ERRORS,
    status_code=status.HTTP_200_OK,
    summary="List all users (administrators only)",
)
async def list_users(
    session: DbSession,
    _admin: CurrentAdmin,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[UserRead]:
    repo = UserRepository(session)
    users = await repo.list(limit=limit, offset=offset, order_by=User.created_at.desc())
    total = await repo.count()
    return Page[UserRead](
        items=[UserRead.model_validate(user) for user in users],
        total=total,
        limit=limit,
        offset=offset,
    )
