"""Password hashing and JWT issuance/verification.

This module is deliberately free of database and framework imports so it can be
unit-tested in isolation and reused by CLI tooling.

Design notes
------------
* Passwords use **Argon2id** (`argon2-cffi`), the current password-hashing
  competition winner, rather than bcrypt: no 72-byte truncation, memory-hard,
  and it exposes a rehash signal when parameters change.
* **Access tokens** are short-lived JWTs sent in the `Authorization` header and
  held only in browser memory.
* **Refresh tokens** are opaque random strings, never JWTs. Only a SHA-256
  digest is persisted, so a database leak cannot be replayed. They are
  delivered in an httpOnly cookie and rotated on every use.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

from app.core.config import settings

_hasher: Final = PasswordHasher()

TOKEN_TYPE_ACCESS: Final = "access"


class TokenError(Exception):
    """Raised when a token is malformed, expired, or fails signature checks."""


@dataclass(frozen=True, slots=True)
class AccessTokenPayload:
    """Validated claims extracted from an access token."""

    subject: str
    role: str
    token_id: str
    issued_at: datetime
    expires_at: datetime


# --------------------------------------------------------------------------- #
# Passwords
# --------------------------------------------------------------------------- #
def hash_password(plain_password: str) -> str:
    """Return an Argon2id hash (includes salt and parameters) for storage."""
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a password against its stored hash, returning False on any mismatch."""
    try:
        return _hasher.verify(password_hash, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses outdated Argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
# Access tokens (JWT)
# --------------------------------------------------------------------------- #
def create_access_token(
    subject: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Issue a signed access token.

    Returns the encoded token and its absolute expiry so callers can report
    `expires_in` to the client without decoding the token again.
    """
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_TTL_MINUTES))
    claims: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": TOKEN_TYPE_ACCESS,
        "iss": settings.JWT_ISSUER,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": uuid.uuid4().hex,
    }
    encoded = jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded, expires_at


def decode_access_token(token: str) -> AccessTokenPayload:
    """Verify and decode an access token, or raise :class:`TokenError`."""
    try:
        claims = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            issuer=settings.JWT_ISSUER,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
    except jwt.PyJWTError as exc:  # expired, bad signature, wrong issuer, ...
        raise TokenError(str(exc)) from exc

    if claims.get("type") != TOKEN_TYPE_ACCESS:
        # Prevents a token minted for another purpose being replayed as an
        # access token.
        raise TokenError("Token is not an access token")

    return AccessTokenPayload(
        subject=str(claims["sub"]),
        role=str(claims.get("role", "student")),
        token_id=str(claims.get("jti", "")),
        issued_at=datetime.fromtimestamp(claims["iat"], tz=UTC),
        expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
    )


# --------------------------------------------------------------------------- #
# Refresh tokens (opaque)
# --------------------------------------------------------------------------- #
def generate_refresh_token() -> str:
    """Return a cryptographically random, URL-safe refresh token."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Digest a refresh token for storage.

    SHA-256 is appropriate here (unlike for passwords) because the input is
    already 384 bits of entropy, so brute-forcing the digest is infeasible and
    lookups must stay fast and deterministic.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def refresh_token_expiry(now: datetime | None = None) -> datetime:
    """Absolute expiry for a newly issued refresh token."""
    return (now or datetime.now(UTC)) + timedelta(days=settings.REFRESH_TOKEN_TTL_DAYS)


def constant_time_compare(left: str, right: str) -> bool:
    """Timing-safe string comparison."""
    return secrets.compare_digest(left, right)
