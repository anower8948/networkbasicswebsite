"""Email verification and password reset.

Token handling mirrors refresh tokens: the value handed to the user is a random
opaque string, and only its SHA-256 digest is stored. A database leak therefore
yields nothing replayable.

Account enumeration
-------------------
"Forgot password" and "resend verification" both respond identically whether or
not the address exists. An endpoint that says "no account with that email" is a
free account-existence oracle, and these two are the easiest to probe because
they need no credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.datetime_utils import as_utc, utcnow
from app.core.exceptions import InvalidToken
from app.core.logging import get_logger
from app.core.security import (
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
)
from app.models.enums import TokenPurpose
from app.models.user import User, VerificationToken
from app.repositories.user import RefreshTokenRepository, UserRepository
from app.repositories.verification import VerificationTokenRepository
from app.services.email_service import EmailService

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IssuedVerification:
    """A freshly minted token plus the account it belongs to."""

    raw_token: str
    user: User


class VerificationService:
    """Issues and consumes single-use email tokens."""

    def __init__(self, session: AsyncSession, email: EmailService | None = None) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.tokens = VerificationTokenRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.email = email or EmailService()

    # ------------------------------------------------------------------ #
    # Issuing
    # ------------------------------------------------------------------ #
    async def _issue(self, user: User, purpose: TokenPurpose) -> str:
        """Retire outstanding tokens of this purpose and mint a new one."""
        await self.tokens.invalidate_outstanding(user.id, purpose)

        raw_token = generate_refresh_token()
        ttl = (
            timedelta(hours=settings.EMAIL_VERIFICATION_TTL_HOURS)
            if purpose is TokenPurpose.EMAIL_VERIFICATION
            else timedelta(minutes=settings.PASSWORD_RESET_TTL_MINUTES)
        )

        self.tokens.add(
            VerificationToken(
                user_id=user.id,
                token_hash=hash_refresh_token(raw_token),
                purpose=purpose,
                expires_at=utcnow() + ttl,
            )
        )
        await self.session.flush()
        return raw_token

    async def send_verification_email(self, user: User) -> None:
        """Issue a verification link and mail it. No-op for verified accounts."""
        if user.is_email_verified:
            return

        raw_token = await self._issue(user, TokenPurpose.EMAIL_VERIFICATION)
        await self.session.commit()
        await self.email.send_email_verification(
            to=user.email, name=user.display_name, token=raw_token
        )
        logger.info("Verification email issued", extra={"user_id": str(user.id)})

    async def request_password_reset(self, email: str) -> None:
        """Mail a reset link if the address is registered.

        Returns without signalling either way; see the module docstring.
        """
        user = await self.users.get_by_email(email)
        if user is None or not user.is_active:
            logger.info(
                "Password reset requested for unknown or inactive address",
                extra={"email_domain": email.rsplit("@", 1)[-1]},
            )
            return

        raw_token = await self._issue(user, TokenPurpose.PASSWORD_RESET)
        await self.session.commit()
        await self.email.send_password_reset(to=user.email, name=user.display_name, token=raw_token)
        logger.info("Password reset email issued", extra={"user_id": str(user.id)})

    # ------------------------------------------------------------------ #
    # Consuming
    # ------------------------------------------------------------------ #
    async def _consume(self, raw_token: str, purpose: TokenPurpose) -> User:
        """Validate a token, mark it used, and return its owner."""
        stored = await self.tokens.get_by_hash(hash_refresh_token(raw_token))

        if stored is None or stored.purpose is not purpose:
            # Same error for "no such token" and "wrong purpose", so a reset
            # token cannot be probed against the verification endpoint to learn
            # that it is valid.
            raise InvalidToken("This link is not valid.")
        if stored.consumed_at is not None:
            raise InvalidToken("This link has already been used.")
        if as_utc(stored.expires_at) <= utcnow():
            raise InvalidToken("This link has expired.")

        user = await self.users.get_with_stats(stored.user_id)
        if user is None:
            raise InvalidToken("This link is not valid.")

        stored.consumed_at = utcnow()
        return user

    async def verify_email(self, raw_token: str) -> User:
        user = await self._consume(raw_token, TokenPurpose.EMAIL_VERIFICATION)
        user.is_email_verified = True
        await self.session.commit()
        logger.info("Email verified", extra={"user_id": str(user.id)})
        return user

    async def reset_password(self, raw_token: str, new_password: str) -> User:
        """Set a new password from a reset link and sign out everywhere.

        Revoking every session matters: if the reset was triggered because an
        attacker had access, leaving their session alive would defeat the point.
        Verifying the email as a side effect is safe — receiving the link proves
        control of the mailbox.
        """
        user = await self._consume(raw_token, TokenPurpose.PASSWORD_RESET)

        user.hashed_password = hash_password(new_password)
        user.tokens_valid_from = utcnow()
        user.is_email_verified = True
        await self.refresh_tokens.revoke_all_for_user(user.id)

        await self.session.commit()
        logger.info("Password reset completed", extra={"user_id": str(user.id)})

        await self.email.send_password_changed_notice(to=user.email, name=user.display_name)
        return user
