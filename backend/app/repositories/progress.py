"""Queries over the XP ledger."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select

from app.models.enums import XPReason
from app.models.gamification import XPTransaction
from app.repositories.base import BaseRepository


class XPTransactionRepository(BaseRepository[XPTransaction]):
    model = XPTransaction

    async def total_for_user(self, user_id: uuid.UUID) -> int:
        """Sum the ledger — the authoritative XP total."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == user_id
            )
        )
        return int(result.scalar_one())

    async def exists_for_reference(
        self,
        user_id: uuid.UUID,
        reason: XPReason,
        reference_type: str,
        reference_id: uuid.UUID,
    ) -> bool:
        """True when this exact grant was already made.

        Backs idempotent XP: replaying a lesson completion must not pay twice.
        """
        result = await self.session.execute(
            select(XPTransaction.id)
            .where(
                XPTransaction.user_id == user_id,
                XPTransaction.reason == reason,
                XPTransaction.reference_type == reference_type,
                XPTransaction.reference_id == reference_id,
            )
            .limit(1)
        )
        return result.first() is not None

    async def recent_for_user(
        self, user_id: uuid.UUID, *, limit: int = 20, offset: int = 0
    ) -> Sequence[XPTransaction]:
        result = await self.session.execute(
            select(XPTransaction)
            .where(XPTransaction.user_id == user_id)
            .order_by(XPTransaction.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()

    async def sum_since(self, user_id: uuid.UUID, since: datetime) -> int:
        """XP earned since an instant — powers "this week" style figures."""
        result = await self.session.execute(
            select(func.coalesce(func.sum(XPTransaction.amount), 0)).where(
                XPTransaction.user_id == user_id,
                XPTransaction.created_at >= since,
            )
        )
        return int(result.scalar_one())
