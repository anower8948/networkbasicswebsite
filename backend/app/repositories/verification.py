"""Queries over single-use verification tokens."""

from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select, update

from app.core.datetime_utils import utcnow
from app.models.enums import TokenPurpose
from app.models.user import VerificationToken
from app.repositories.base import BaseRepository


class VerificationTokenRepository(BaseRepository[VerificationToken]):
    model = VerificationToken

    async def get_by_hash(self, token_hash: str) -> VerificationToken | None:
        result = await self.session.execute(
            select(VerificationToken).where(VerificationToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def invalidate_outstanding(self, user_id: uuid.UUID, purpose: TokenPurpose) -> int:
        """Consume any live tokens of this purpose for the user.

        Issuing a new link must retire the previous one, otherwise every reset
        email ever sent stays usable until it expires — each one an independent
        chance for an old message to be replayed out of a mailbox.
        """
        result = await self.session.execute(
            update(VerificationToken)
            .where(
                VerificationToken.user_id == user_id,
                VerificationToken.purpose == purpose,
                VerificationToken.consumed_at.is_(None),
            )
            .values(consumed_at=utcnow())
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def delete_expired(self) -> int:
        """Housekeeping: drop tokens that can no longer be used."""
        result = await self.session.execute(
            delete(VerificationToken).where(VerificationToken.expires_at < utcnow())
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)
