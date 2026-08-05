"""Achievements, leaderboards, and certificates.

One module rather than three because they are one feature from the learner's
point of view — the recognition surface — and splitting them would leave three
files of a dozen lines each.

The certificate verification endpoint is the only **public** route here, and it
is public on purpose: a verification code is meant to be given to an employer.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentAdmin, CurrentUser, DbSession, get_optional_user
from app.models.user import User
from app.schemas.common import ErrorResponse
from app.schemas.gamification import (
    AchievementList,
    CertificateRead,
    CertificateVerification,
    Leaderboard,
)
from app.services.achievement_service import AchievementService
from app.services.certificate_service import CertificateService
from app.services.leaderboard_service import LeaderboardService

router = APIRouter(tags=["Recognition"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}

OptionalUser = Annotated[User | None, Depends(get_optional_user)]


# --------------------------------------------------------------------------- #
# Achievements
# --------------------------------------------------------------------------- #
@router.get(
    "/achievements",
    response_model=AchievementList,
    responses=_ERRORS,
    summary="Every badge, with progress toward the unearned ones",
)
async def list_achievements(session: DbSession, user: CurrentUser) -> AchievementList:
    """Secret badges are omitted until earned — showing their titles greyed out
    would give away exactly what this endpoint is meant to keep back."""
    return await AchievementService(session).list_for_user(user)


@router.post(
    "/achievements/evaluate",
    response_model=AchievementList,
    responses=_ERRORS,
    summary="Re-check every badge against current progress",
)
async def evaluate_achievements(session: DbSession, user: CurrentUser) -> AchievementList:
    """Badges are normally awarded as their triggering event happens. This
    exists for the case where criteria were added after a learner had already
    met them — and it is idempotent, so calling it is always safe."""
    service = AchievementService(session)
    await service.evaluate(user)
    return await service.list_for_user(user)


# --------------------------------------------------------------------------- #
# Leaderboards
# --------------------------------------------------------------------------- #
@router.get(
    "/leaderboard",
    response_model=Leaderboard,
    summary="Top learners, all-time or over a recent window",
)
async def get_leaderboard(
    session: DbSession,
    user: OptionalUser,
    scope: Literal["all_time", "monthly", "weekly"] = "all_time",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Leaderboard:
    """Includes the signed-in learner's own standing even when they are outside
    the returned page."""
    return await LeaderboardService(session).get(scope, viewer=user, limit=limit)


# --------------------------------------------------------------------------- #
# Certificates
# --------------------------------------------------------------------------- #
@router.get(
    "/certificates",
    response_model=list[CertificateRead],
    responses=_ERRORS,
    summary="This learner's certificates",
)
async def list_certificates(session: DbSession, user: CurrentUser) -> list[CertificateRead]:
    return await CertificateService(session).list_for_user(user)


@router.post(
    "/certificates/{course_slug}",
    response_model=CertificateRead,
    responses=_ERRORS,
    summary="Claim the certificate for a completed course",
)
async def issue_certificate(
    course_slug: str, session: DbSession, user: CurrentUser
) -> CertificateRead:
    """Idempotent: claiming twice returns the certificate already issued."""
    return await CertificateService(session).issue(user, course_slug)


@router.get(
    "/certificates/verify/{code}",
    response_model=CertificateVerification,
    summary="Publicly verify a certificate",
)
async def verify_certificate(code: str, session: DbSession) -> CertificateVerification:
    """Public and unauthenticated — the code is designed to go on a CV.

    An unknown code answers `valid: false` rather than 404, so this cannot be
    used to tell "no such certificate" from "revoked certificate".
    """
    return await CertificateService(session).verify(code)


@router.delete(
    "/certificates/{certificate_id}",
    response_model=CertificateRead,
    responses=_ERRORS,
    summary="Revoke a certificate",
)
async def revoke_certificate(
    certificate_id: uuid.UUID, session: DbSession, admin: CurrentAdmin
) -> CertificateRead:
    """Revoked, never deleted: the code must keep resolving, to `valid: false`."""
    return await CertificateService(session).revoke(certificate_id)
