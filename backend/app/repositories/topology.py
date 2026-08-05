"""Queries over saved topologies."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select

from app.models.lab import Topology
from app.repositories.base import BaseRepository


class TopologyRepository(BaseRepository[Topology]):
    model = Topology

    async def list_for_owner(
        self, owner_id: uuid.UUID, *, limit: int = 50, offset: int = 0
    ) -> Sequence[Topology]:
        result = await self.session.execute(
            select(Topology)
            .where(Topology.owner_id == owner_id)
            .order_by(Topology.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def count_for_owner(self, owner_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(Topology.id)).where(Topology.owner_id == owner_id)
        )
        return int(result.scalar_one())

    async def list_templates(self) -> Sequence[Topology]:
        """Instructor-authored starting points for the "new from template" gallery."""
        result = await self.session.execute(
            select(Topology).where(Topology.is_template.is_(True)).order_by(Topology.name)
        )
        return result.scalars().all()

    async def get_for_owner(self, topology_id: uuid.UUID, owner_id: uuid.UUID) -> Topology | None:
        """Fetch only if this owner holds it.

        Ownership is part of the query rather than a check afterwards, so there
        is no path that loads someone else's topology into memory first.
        """
        result = await self.session.execute(
            select(Topology).where(Topology.id == topology_id, Topology.owner_id == owner_id)
        )
        return result.scalar_one_or_none()

    async def get_readable(
        self, topology_id: uuid.UUID, viewer_id: uuid.UUID | None
    ) -> Topology | None:
        """Fetch if the viewer owns it, or if it is public or a template."""
        stmt = select(Topology).where(Topology.id == topology_id)
        result = await self.session.execute(stmt)
        topology = result.scalar_one_or_none()

        if topology is None:
            return None
        if topology.is_public or topology.is_template:
            return topology
        if viewer_id is not None and topology.owner_id == viewer_id:
            return topology
        return None
