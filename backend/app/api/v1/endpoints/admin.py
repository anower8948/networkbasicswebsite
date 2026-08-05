"""Instructor and admin tooling.

Two privilege levels, and the split is the point:

* **Instructor** sees content performance and the class roster — what they need
  to teach with.
* **Admin** additionally authors labs and revokes certificates.

Nothing here exposes a per-learner activity trail. See `app.schemas.analytics`
for why that line is drawn where it is.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentAdmin, CurrentInstructor, DbSession
from app.core.exceptions import ConflictError, NotFoundError
from app.models.enums import LabKind, ScenarioType
from app.models.lab import Lab
from app.repositories.lab import LabRepository
from app.schemas.analytics import AnalyticsReport, RosterEntry
from app.schemas.common import ErrorResponse, MessageResponse
from app.schemas.lab import LabWrite
from app.services.analytics_service import AnalyticsService

router = APIRouter(prefix="/admin", tags=["Admin"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
@router.get(
    "/analytics",
    response_model=AnalyticsReport,
    responses=_ERRORS,
    summary="Platform and content performance",
)
async def get_analytics(session: DbSession, instructor: CurrentInstructor) -> AnalyticsReport:
    """Aggregate only. A lab with a low pass rate and a high hint average is
    usually a badly worded lab, which is what this is for."""
    return await AnalyticsService(session).report()


@router.get(
    "/roster",
    response_model=list[RosterEntry],
    responses=_ERRORS,
    summary="Learners and their standing",
)
async def get_roster(
    session: DbSession,
    instructor: CurrentInstructor,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[RosterEntry]:
    return await AnalyticsService(session).roster(limit=limit, offset=offset)


# --------------------------------------------------------------------------- #
# Lab authoring
# --------------------------------------------------------------------------- #
def _apply(lab: Lab, payload: LabWrite) -> Lab:
    """Write an authoring payload onto a lab row.

    Everything is dumped through the validated models, so a rule that would not
    parse cannot be persisted — the same guarantee the seeder relies on.
    """
    lab.title = payload.title
    lab.description = payload.description
    lab.kind = LabKind(payload.kind)
    lab.scenario_type = ScenarioType(payload.scenario_type) if payload.scenario_type else None
    lab.difficulty = payload.difficulty
    lab.requirements = list(payload.requirements)
    lab.objectives = [item.model_dump(mode="json", by_alias=True) for item in payload.objectives]
    lab.initial_topology = payload.initial_topology.model_dump(mode="json", by_alias=True)
    lab.grading_rules = [
        rule.model_dump(mode="json", by_alias=True) for rule in payload.grading_rules
    ]
    lab.fault_injections = [
        fault.model_dump(mode="json", by_alias=True) for fault in payload.fault_injections
    ]
    lab.estimated_minutes = payload.estimated_minutes
    lab.time_limit_seconds = payload.time_limit_seconds
    lab.passing_score = payload.passing_score
    lab.xp_reward = payload.xp_reward
    lab.is_published = payload.is_published
    return lab


@router.post(
    "/labs",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Author a lab",
)
async def create_lab(payload: LabWrite, session: DbSession, admin: CurrentAdmin) -> MessageResponse:
    labs = LabRepository(session)
    if await labs.get_by_slug(payload.slug) is not None:
        raise ConflictError("A lab with that slug already exists.")

    labs.add(_apply(Lab(slug=payload.slug), payload))
    await session.commit()
    return MessageResponse(message=f"Lab '{payload.slug}' created.")


@router.put(
    "/labs/{lab_id}",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Replace a lab",
)
async def update_lab(
    lab_id: uuid.UUID, payload: LabWrite, session: DbSession, admin: CurrentAdmin
) -> MessageResponse:
    labs = LabRepository(session)
    lab = await labs.get(lab_id)
    if lab is None:
        raise NotFoundError("Lab not found.")

    lab.slug = payload.slug
    _apply(lab, payload)
    await session.commit()
    return MessageResponse(message=f"Lab '{payload.slug}' updated.")


@router.delete(
    "/labs/{lab_id}",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Delete a lab",
)
async def delete_lab(lab_id: uuid.UUID, session: DbSession, admin: CurrentAdmin) -> MessageResponse:
    labs = LabRepository(session)
    lab = await labs.get(lab_id)
    if lab is None:
        raise NotFoundError("Lab not found.")

    # Attempts cascade with the lab. That is deliberate: a deleted lab's
    # attempts reference grading rules that no longer exist and could not be
    # rendered, and the XP already granted lives in the ledger regardless.
    await labs.delete(lab)
    await session.commit()
    return MessageResponse(message="Lab deleted.")
