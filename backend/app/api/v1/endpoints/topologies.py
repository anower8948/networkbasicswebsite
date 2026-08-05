"""Topology editor endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import CurrentUser, DbSession, get_optional_user
from app.models.enums import CableKind
from app.models.lab import Topology
from app.models.user import User
from app.schemas.common import ErrorResponse, MessageResponse, Page
from app.schemas.topology import (
    LinkSuggestion,
    TopologyCreate,
    TopologyDocument,
    TopologyImport,
    TopologyRead,
    TopologySummary,
    TopologyUpdate,
)
from app.services.device_catalog import catalog_payload
from app.services.topology_service import TopologyService

router = APIRouter(prefix="/topologies", tags=["Topologies"])

OptionalUser = Annotated[User | None, Depends(get_optional_user)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _to_read(topology: Topology) -> TopologyRead:
    """Project a stored topology, recomputing cabling warnings on read.

    Warnings are derived rather than stored so that improving the rules
    immediately improves feedback on every existing topology.
    """
    document = TopologyDocument.model_validate(topology.document or {})
    return TopologyRead(
        id=topology.id,
        name=topology.name,
        description=topology.description,
        device_count=topology.device_count,
        schema_version=topology.schema_version,
        is_template=topology.is_template,
        is_public=topology.is_public,
        thumbnail_url=topology.thumbnail_url,
        created_at=topology.created_at,
        updated_at=topology.updated_at,
        document=document,
        issues=document.cable_issues(),
    )


@router.get(
    "/device-catalog",
    summary="Every device kind that can be placed, with its interfaces",
)
async def device_catalog(response: Response) -> list[dict[str, Any]]:
    """Public and static — the palette needs it before anyone signs in.

    Serving it from the backend keeps one definition of what a Catalyst 2960's
    ports are called, shared by the editor, Part 5's configuration forms and
    Part 6's CLI.

    The only endpoint that returns identical bytes to every caller and changes
    only on deploy, so it is the only one worth a public cache. Everything else
    is per-learner and stays `no-store`, which the security middleware applies
    by default.
    """
    response.headers["Cache-Control"] = "public, max-age=3600, stale-while-revalidate=86400"
    return catalog_payload()


@router.get(
    "",
    response_model=Page[TopologySummary],
    responses=_ERRORS,
    summary="List the current user's saved topologies",
)
async def list_topologies(
    session: DbSession,
    user: CurrentUser,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[TopologySummary]:
    service = TopologyService(session)
    items = await service.list_for(user, limit=limit, offset=offset)
    total = await service.topologies.count_for_owner(user.id)

    return Page[TopologySummary](
        items=[TopologySummary.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "",
    response_model=TopologyRead,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Create a topology",
)
async def create_topology(
    payload: TopologyCreate,
    session: DbSession,
    user: CurrentUser,
) -> TopologyRead:
    return _to_read(await TopologyService(session).create(user, payload))


@router.post(
    "/import",
    response_model=TopologyRead,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Import a previously exported topology",
)
async def import_topology(
    payload: TopologyImport,
    session: DbSession,
    user: CurrentUser,
) -> TopologyRead:
    """A malformed or hand-edited file is rejected by the schema, not the canvas."""
    return _to_read(await TopologyService(session).import_document(user, payload))


@router.get(
    "/{topology_id}",
    response_model=TopologyRead,
    responses=_ERRORS,
    summary="Load a topology",
)
async def get_topology(
    topology_id: uuid.UUID,
    session: DbSession,
    user: OptionalUser,
) -> TopologyRead:
    """Readable by its owner, or by anyone if it is public or a template."""
    return _to_read(await TopologyService(session).get(topology_id, user))


@router.get(
    "/{topology_id}/export",
    responses=_ERRORS,
    summary="Export a topology as a portable document",
)
async def export_topology(
    topology_id: uuid.UUID,
    session: DbSession,
    user: OptionalUser,
) -> dict[str, Any]:
    service = TopologyService(session)
    topology = await service.get(topology_id, user)
    return service.export_document(topology)


@router.patch(
    "/{topology_id}",
    response_model=TopologyRead,
    responses=_ERRORS,
    summary="Save changes to a topology",
)
async def update_topology(
    topology_id: uuid.UUID,
    payload: TopologyUpdate,
    session: DbSession,
    user: CurrentUser,
) -> TopologyRead:
    return _to_read(await TopologyService(session).update(topology_id, user, payload))


@router.post(
    "/{topology_id}/duplicate",
    response_model=TopologyRead,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Copy a topology into your own workspace",
)
async def duplicate_topology(
    topology_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> TopologyRead:
    return _to_read(await TopologyService(session).duplicate(topology_id, user))


@router.delete(
    "/{topology_id}",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Delete a topology",
)
async def delete_topology(
    topology_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> MessageResponse:
    await TopologyService(session).delete(topology_id, user)
    return MessageResponse(message="Topology deleted.")


@router.post(
    "/suggest-link",
    response_model=LinkSuggestion,
    responses=_ERRORS,
    summary="Choose interfaces and a cable for a new link",
)
async def suggest_link(
    document: TopologyDocument,
    session: DbSession,
    user: CurrentUser,
    source: str = Query(description="Source device id within the document"),
    target: str = Query(description="Target device id within the document"),
    cable: CableKind | None = Query(default=None),
) -> LinkSuggestion:
    """Picks the lowest free compatible port on each end and infers the cable.

    Stateless: the editor posts its in-memory document, so this works before a
    topology has ever been saved.
    """
    return TopologyService(session).suggest_link(document, source, target, cable)
