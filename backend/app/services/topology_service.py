"""Saving, loading, and exchanging topologies.

The service owns two things the endpoints must not duplicate: ownership
enforcement, and keeping the denormalised `device_count` in step with the
document it summarises.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.enums import CableKind, DeviceKind
from app.models.lab import Topology
from app.models.user import User
from app.repositories.topology import TopologyRepository
from app.schemas.topology import (
    TOPOLOGY_SCHEMA_VERSION,
    LinkSuggestion,
    TopologyCreate,
    TopologyDocument,
    TopologyImport,
    TopologyUpdate,
)
from app.services.device_catalog import cable_warning, recommended_cable, spec_for

logger = get_logger(__name__)

# A generous ceiling that still bounds one account's storage.
MAX_TOPOLOGIES_PER_USER = 100


class TopologyNotFound(NotFoundError):
    code = "topology_not_found"
    message = "Topology not found."


class TopologyLimitReached(ConflictError):
    code = "topology_limit_reached"
    message = f"You can save up to {MAX_TOPOLOGIES_PER_USER} topologies."


class NoFreeInterface(ConflictError):
    code = "no_free_interface"
    message = "That device has no free interface of a compatible type."


class TopologyService:
    """Use cases for the topology editor."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.topologies = TopologyRepository(session)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def list_for(self, user: User, *, limit: int = 50, offset: int = 0) -> Sequence[Topology]:
        return await self.topologies.list_for_owner(user.id, limit=limit, offset=offset)

    async def get(self, topology_id: uuid.UUID, viewer: User | None) -> Topology:
        topology = await self.topologies.get_readable(topology_id, viewer.id if viewer else None)
        if topology is None:
            # Same error whether it is missing or someone else's private work,
            # so this endpoint cannot enumerate topology ids.
            raise TopologyNotFound()
        return topology

    async def get_owned(self, topology_id: uuid.UUID, user: User) -> Topology:
        topology = await self.topologies.get_for_owner(topology_id, user.id)
        if topology is None:
            raise TopologyNotFound()
        return topology

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def create(self, user: User, payload: TopologyCreate) -> Topology:
        if await self.topologies.count_for_owner(user.id) >= MAX_TOPOLOGIES_PER_USER:
            raise TopologyLimitReached()

        topology = Topology(
            owner_id=user.id,
            name=payload.name,
            description=payload.description,
            document=payload.document.model_dump(mode="json", by_alias=True),
            schema_version=payload.document.schema_version,
            device_count=len(payload.document.devices),
        )
        self.topologies.add(topology)
        await self.session.commit()

        logger.info(
            "Topology created",
            extra={"user_id": str(user.id), "topology_id": str(topology.id)},
        )
        return topology

    async def update(self, topology_id: uuid.UUID, user: User, payload: TopologyUpdate) -> Topology:
        topology = await self.get_owned(topology_id, user)

        if payload.name is not None:
            topology.name = payload.name
        if payload.description is not None:
            topology.description = payload.description
        if payload.document is not None:
            topology.document = payload.document.model_dump(mode="json", by_alias=True)
            topology.schema_version = payload.document.schema_version
            # Derived from the document rather than trusted from the client, so
            # the two can never disagree.
            topology.device_count = len(payload.document.devices)

        await self.session.commit()
        return topology

    async def delete(self, topology_id: uuid.UUID, user: User) -> None:
        topology = await self.get_owned(topology_id, user)
        await self.topologies.delete(topology)
        await self.session.commit()
        logger.info(
            "Topology deleted",
            extra={"user_id": str(user.id), "topology_id": str(topology_id)},
        )

    async def duplicate(self, topology_id: uuid.UUID, user: User) -> Topology:
        """Copy a topology the viewer can read into their own workspace.

        Templates and public designs are copied rather than shared, so editing
        a copy never mutates someone else's original.
        """
        source = await self.get(topology_id, user)
        if await self.topologies.count_for_owner(user.id) >= MAX_TOPOLOGIES_PER_USER:
            raise TopologyLimitReached()

        copy = Topology(
            owner_id=user.id,
            name=f"{source.name} (copy)",
            description=source.description,
            document=source.document,
            schema_version=source.schema_version,
            device_count=source.device_count,
        )
        self.topologies.add(copy)
        await self.session.commit()
        return copy

    async def import_document(self, user: User, payload: TopologyImport) -> Topology:
        """Create a topology from an exported file.

        The document has already been validated by the schema, so a hand-edited
        or corrupted export fails at the boundary rather than on the canvas.
        """
        return await self.create(
            user,
            TopologyCreate(
                name=payload.name or "Imported topology",
                description=None,
                document=payload.document,
            ),
        )

    @staticmethod
    def export_document(topology: Topology) -> dict[str, object]:
        """The portable file format.

        Deliberately excludes ids, ownership and timestamps: an export should
        be a description of a network, not a database row.
        """
        return {
            "format": "network-learning-platform/topology",
            "schemaVersion": topology.schema_version or TOPOLOGY_SCHEMA_VERSION,
            "name": topology.name,
            "description": topology.description,
            "document": topology.document,
        }

    # ------------------------------------------------------------------ #
    # Cabling assistance
    # ------------------------------------------------------------------ #
    def suggest_link(
        self,
        document: TopologyDocument,
        source_device_id: str,
        target_device_id: str,
        cable: CableKind | None = None,
    ) -> LinkSuggestion:
        """Choose interfaces and a cable when two devices are joined.

        The editor connects whole devices — asking a learner to pick
        `FastEthernet0/7` from a list of 26 before they have learned what a port
        is would be hostile. This picks the lowest free port of a compatible
        type on each end and infers the cable, both of which stay editable.
        """
        devices = {device.id: device for device in document.devices}
        source = devices.get(source_device_id)
        target = devices.get(target_device_id)
        if source is None or target is None:
            raise TopologyNotFound("One of the devices is not in this topology.")

        occupied = {
            (endpoint.device_id, endpoint.interface)
            for link in document.links
            for endpoint in (link.source, link.target)
        }

        source_interface = self._first_free_interface(source.kind, source.id, occupied)
        target_interface = self._first_free_interface(target.kind, target.id, occupied)

        chosen = cable or recommended_cable(
            source.kind, source_interface, target.kind, target_interface
        )
        warning = cable_warning(
            source.kind, source_interface, target.kind, target_interface, chosen
        )

        return LinkSuggestion(
            source_interface=source_interface,
            target_interface=target_interface,
            cable=chosen,
            warning=warning,
        )

    @staticmethod
    def _first_free_interface(
        kind: DeviceKind, device_id: str, occupied: set[tuple[str, str]]
    ) -> str:
        for entry in spec_for(kind).interfaces():
            if not entry["connectable"]:
                continue  # console ports carry no traffic
            name = str(entry["name"])
            if (device_id, name) not in occupied:
                return name
        raise NoFreeInterface()
