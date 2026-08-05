"""Queries over users, refresh tokens, and learner statistics."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.models.user import RefreshToken, User, UserStats
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_with_stats(self, user_id: uuid.UUID) -> User | None:
        result = await self.session.execute(
            select(User).options(selectinload(User.stats)).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).options(selectinload(User.stats)).where(User.email == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        # Usernames are stored as typed but compared case-insensitively so
        # "Alice" and "alice" cannot both be registered.
        result = await self.session.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none()

    async def email_or_username_exists(self, email: str, username: str) -> User | None:
        """Single round trip for the registration uniqueness check."""
        result = await self.session.execute(
            select(User).where(
                or_(
                    User.email == email.lower(),
                    func.lower(User.username) == username.lower(),
                )
            )
        )
        return result.scalars().first()

    async def is_empty(self) -> bool:
        """True when no account exists yet — drives first-user admin bootstrap."""
        result = await self.session.execute(select(User.id).limit(1))
        return result.first() is None

    async def touch_last_login(self, user: User) -> None:
        user.last_login_at = datetime.now(UTC)


class UserStatsRepository(BaseRepository[UserStats]):
    model = UserStats

    async def get_for_user(self, user_id: uuid.UUID) -> UserStats | None:
        result = await self.session.execute(select(UserStats).where(UserStats.user_id == user_id))
        return result.scalar_one_or_none()

    async def leaderboard(self, *, limit: int = 20, offset: int = 0) -> Sequence[UserStats]:
        result = await self.session.execute(
            select(UserStats)
            .options(selectinload(UserStats.user))
            .order_by(UserStats.total_xp.desc())
            .limit(limit)
            .offset(offset)
        )
        return result.scalars().all()


class RefreshTokenRepository(BaseRepository[RefreshToken]):
    model = RefreshToken

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self.session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def list_active_for_user(self, user_id: uuid.UUID) -> Sequence[RefreshToken]:
        now = datetime.now(UTC)
        result = await self.session.execute(
            select(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > now,
            )
            .order_by(RefreshToken.issued_at.desc())
        )
        return result.scalars().all()

    async def revoke_family(self, family_id: uuid.UUID) -> int:
        """Revoke every live token in a family.

        Called when a already-rotated token is replayed: that means the token
        leaked, so the whole login session is burned rather than just the one
        credential.
        """
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> int:
        result = await self.session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)

    async def delete_expired(self, *, before: datetime | None = None) -> int:
        """Housekeeping: drop tokens that expired before `before`."""
        cutoff = before or datetime.now(UTC)
        result = await self.session.execute(
            delete(RefreshToken).where(RefreshToken.expires_at < cutoff)
        )
        return int(cast(CursorResult[Any], result).rowcount or 0)
