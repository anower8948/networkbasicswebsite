"""Authentication use cases.

Owns registration, login, refresh-token rotation, logout, and password change.
Raises domain exceptions from `app.core.exceptions`; it never imports FastAPI,
so the whole flow is testable without an HTTP layer.

Refresh token rotation
----------------------
Every refresh issues a brand-new token and revokes the one presented. All
tokens descending from a single login share a `family_id`. Presenting a token
that was already rotated means a copy leaked, so the entire family is revoked
and the attacker and the victim are both logged out — the standard OAuth 2.0
BCP reuse-detection design.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import as_utc
from app.core.exceptions import (
    EmailAlreadyRegistered,
    InactiveAccount,
    InvalidCredentials,
    InvalidToken,
    UsernameAlreadyTaken,
)
from app.core.logging import get_logger
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    refresh_token_expiry,
    verify_password,
)
from app.models.enums import UserRole
from app.models.user import RefreshToken, User, UserStats
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.schemas.user import UserCreate

logger = get_logger(__name__)

# Argon2 verification of a throwaway hash, used to keep the timing of "unknown
# email" indistinguishable from "wrong password". Computed once at import.
_DUMMY_HASH = hash_password("timing-equalisation-placeholder")


@dataclass(frozen=True, slots=True)
class ClientContext:
    """Request metadata recorded against an issued refresh token."""

    user_agent: str | None = None
    ip_address: str | None = None


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    """Result of any operation that establishes or extends a session."""

    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    user: User

    @property
    def expires_in(self) -> int:
        """Access token lifetime in whole seconds."""
        delta = self.access_expires_at - datetime.now(UTC)
        return max(0, int(delta.total_seconds()))


class AuthService:
    """Coordinates the authentication domain."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    # ------------------------------------------------------------------ #
    # Registration
    # ------------------------------------------------------------------ #
    async def register(self, payload: UserCreate, context: ClientContext) -> IssuedTokens:
        """Create an account and open a session for it."""
        existing = await self.users.email_or_username_exists(payload.email, payload.username)
        if existing is not None:
            # Distinguishing the two is safe: both are discoverable by simply
            # attempting a registration, and a vague error makes the form
            # unusable.
            if existing.email == payload.email.lower():
                raise EmailAlreadyRegistered()
            raise UsernameAlreadyTaken()

        # The very first account on a fresh instance becomes the administrator,
        # so a new deployment is usable without a manual database edit.
        role = UserRole.STUDENT
        if settings.BOOTSTRAP_FIRST_USER_AS_ADMIN and await self.users.is_empty():
            role = UserRole.ADMIN
            logger.info(
                "Bootstrapping first account as administrator", extra={"username": payload.username}
            )

        user = User(
            email=payload.email.lower(),
            username=payload.username,
            hashed_password=hash_password(payload.password),
            full_name=payload.full_name,
            role=role,
        )
        user.stats = UserStats()
        self.users.add(user)

        try:
            await self.session.flush()
        except IntegrityError as exc:
            # Two concurrent registrations can both pass the check above; the
            # unique index is the real arbiter.
            await self.session.rollback()
            raise EmailAlreadyRegistered() from exc

        tokens = await self._issue_session(user, context, family_id=uuid.uuid4())
        await self.session.commit()
        logger.info("User registered", extra={"user_id": str(user.id), "role": role.value})
        return tokens

    # ------------------------------------------------------------------ #
    # Login
    # ------------------------------------------------------------------ #
    async def authenticate(self, email: str, password: str, context: ClientContext) -> IssuedTokens:
        """Verify credentials and open a session."""
        user = await self.users.get_by_email(email)

        if user is None:
            # Burn comparable CPU time so response latency does not reveal
            # whether the address is registered.
            verify_password(password, _DUMMY_HASH)
            raise InvalidCredentials()

        if not verify_password(password, user.hashed_password):
            raise InvalidCredentials()

        if not user.is_active:
            raise InactiveAccount()

        # Transparently upgrade the stored hash when Argon2 parameters change.
        if password_needs_rehash(user.hashed_password):
            user.hashed_password = hash_password(password)

        await self.users.touch_last_login(user)
        tokens = await self._issue_session(user, context, family_id=uuid.uuid4())
        await self.session.commit()
        logger.info("User logged in", extra={"user_id": str(user.id)})
        return tokens

    # ------------------------------------------------------------------ #
    # Refresh
    # ------------------------------------------------------------------ #
    async def refresh(self, raw_token: str, context: ClientContext) -> IssuedTokens:
        """Rotate a refresh token and mint a new access token."""
        token_hash = hash_refresh_token(raw_token)
        stored = await self.refresh_tokens.get_by_hash(token_hash)

        if stored is None:
            raise InvalidToken("Refresh token not recognised.")

        if stored.is_revoked:
            # Reuse detection: this token was already rotated, so a copy is in
            # circulation. Burn the entire family.
            revoked = await self.refresh_tokens.revoke_family(stored.family_id)
            await self.session.commit()
            logger.warning(
                "Refresh token reuse detected; family revoked",
                extra={
                    "user_id": str(stored.user_id),
                    "family_id": str(stored.family_id),
                    "revoked_count": revoked,
                },
            )
            raise InvalidToken("Refresh token has already been used.")

        if as_utc(stored.expires_at) <= datetime.now(UTC):
            raise InvalidToken("Refresh token has expired.")

        user = await self.users.get_with_stats(stored.user_id)
        if user is None:
            raise InvalidToken("Refresh token not recognised.")
        if not user.is_active:
            raise InactiveAccount()

        # Rotate: revoke the presented token and link it to its successor.
        now = datetime.now(UTC)
        stored.revoked_at = now
        tokens = await self._issue_session(user, context, family_id=stored.family_id)
        await self.session.flush()

        replacement = await self.refresh_tokens.get_by_hash(
            hash_refresh_token(tokens.refresh_token)
        )
        if replacement is not None:
            stored.replaced_by_id = replacement.id

        await self.session.commit()
        return tokens

    # ------------------------------------------------------------------ #
    # Logout
    # ------------------------------------------------------------------ #
    async def logout(self, raw_token: str | None) -> None:
        """Revoke the session behind the presented refresh token.

        Silently succeeds on an unknown token: logout must be idempotent, and
        a client with no valid cookie is already logged out.
        """
        if not raw_token:
            return
        stored = await self.refresh_tokens.get_by_hash(hash_refresh_token(raw_token))
        if stored is None:
            return
        # Revoke the family, not just this token, so a stale copy on another
        # tab cannot silently re-establish the session.
        await self.refresh_tokens.revoke_family(stored.family_id)
        await self.session.commit()
        logger.info("User logged out", extra={"user_id": str(stored.user_id)})

    async def logout_everywhere(self, user: User) -> int:
        """Revoke every session for a user."""
        count = await self.refresh_tokens.revoke_all_for_user(user.id)
        await self.session.commit()
        return count

    # ------------------------------------------------------------------ #
    # Password change
    # ------------------------------------------------------------------ #
    async def change_password(
        self, user: User, current_password: str, new_password: str, context: ClientContext
    ) -> IssuedTokens:
        """Replace the password and re-establish a single fresh session.

        Every existing refresh token is revoked and `tokens_valid_from` is
        advanced, which also invalidates outstanding access tokens immediately
        rather than letting them run out their remaining TTL.
        """
        if not verify_password(current_password, user.hashed_password):
            raise InvalidCredentials("The current password is incorrect.")

        user.hashed_password = hash_password(new_password)
        user.tokens_valid_from = datetime.now(UTC)
        await self.refresh_tokens.revoke_all_for_user(user.id)

        tokens = await self._issue_session(user, context, family_id=uuid.uuid4())
        await self.session.commit()
        logger.info("Password changed", extra={"user_id": str(user.id)})
        return tokens

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    async def _issue_session(
        self, user: User, context: ClientContext, *, family_id: uuid.UUID
    ) -> IssuedTokens:
        """Mint an access/refresh pair and persist the refresh token's digest."""
        access_token, access_expires_at = create_access_token(str(user.id), user.role.value)

        raw_refresh = generate_refresh_token()
        expires_at = refresh_token_expiry()
        self.refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                token_hash=hash_refresh_token(raw_refresh),
                family_id=family_id,
                expires_at=expires_at,
                user_agent=(context.user_agent or "")[:400] or None,
                ip_address=context.ip_address,
            )
        )
        await self.session.flush()

        return IssuedTokens(
            access_token=access_token,
            access_expires_at=access_expires_at,
            refresh_token=raw_refresh,
            refresh_expires_at=expires_at,
            user=user,
        )
