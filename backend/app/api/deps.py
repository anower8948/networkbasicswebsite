"""Shared FastAPI dependencies: session, current user, role guards."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import as_utc
from app.core.exceptions import InactiveAccount, InvalidToken, PermissionDenied
from app.core.security import TokenError, decode_access_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.auth_service import ClientContext
from app.services.user_service import UserService

# auto_error=False so a missing header raises our own 401 envelope rather than
# FastAPI's default `{"detail": ...}` shape.
bearer_scheme = HTTPBearer(auto_error=False, description="Access token")

DbSession = Annotated[AsyncSession, Depends(get_db)]

# Privilege ordering used by `require_role`. A higher-ranked role satisfies any
# requirement below it, so admins never need to be listed explicitly.
_ROLE_RANK: dict[UserRole, int] = {
    UserRole.STUDENT: 0,
    UserRole.INSTRUCTOR: 1,
    UserRole.ADMIN: 2,
}


def get_client_context(request: Request) -> ClientContext:
    """Capture user agent and client IP for refresh-token auditing."""
    # Azure App Service and most reverse proxies put the real client first in
    # X-Forwarded-For; request.client.host would otherwise be the proxy.
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        ip_address: str | None = forwarded.split(",")[0].strip()
    else:
        ip_address = request.client.host if request.client else None

    return ClientContext(
        user_agent=request.headers.get("user-agent"),
        ip_address=ip_address,
    )


async def get_current_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    """Resolve the authenticated user from the bearer access token."""
    if credentials is None or not credentials.credentials:
        raise InvalidToken("Authorization header is missing.")

    try:
        payload = decode_access_token(credentials.credentials)
    except TokenError as exc:
        raise InvalidToken(str(exc)) from exc

    try:
        user_id = uuid.UUID(payload.subject)
    except ValueError as exc:
        raise InvalidToken("Malformed token subject.") from exc

    user = await UserRepository(session).get_with_stats(user_id)
    if user is None:
        # The account was deleted after the token was issued.
        raise InvalidToken("Account no longer exists.")
    if not user.is_active:
        raise InactiveAccount()

    # Tokens minted before a password change are rejected even if unexpired.
    # `iat` is stored with second precision, so the cutoff is truncated to match;
    # otherwise a token issued in the same second would be spuriously rejected.
    if user.tokens_valid_from is not None and payload.issued_at < as_utc(
        user.tokens_valid_from
    ).replace(microsecond=0):
        raise InvalidToken("Token was invalidated by a credential change.")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_optional_user(
    session: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User | None:
    """Resolve the user when a valid token is present, otherwise `None`.

    For endpoints that are public but richer when authenticated, such as the
    course catalogue showing progress bars.
    """
    if credentials is None or not credentials.credentials:
        return None
    try:
        return await get_current_user(session, credentials)
    except (InvalidToken, InactiveAccount):
        return None


def require_role(minimum: UserRole) -> Callable[[User], Awaitable[User]]:
    """Build a dependency asserting at least `minimum` privilege."""

    async def dependency(user: CurrentUser) -> User:
        if _ROLE_RANK[user.role] < _ROLE_RANK[minimum]:
            raise PermissionDenied(f"This action requires the '{minimum.value}' role or higher.")
        return user

    return dependency


require_instructor = require_role(UserRole.INSTRUCTOR)
require_admin = require_role(UserRole.ADMIN)

CurrentInstructor = Annotated[User, Depends(require_instructor)]
CurrentAdmin = Annotated[User, Depends(require_admin)]


async def get_user_service(session: DbSession) -> UserService:
    return UserService(session)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]

__all__ = [
    "CurrentAdmin",
    "CurrentInstructor",
    "CurrentUser",
    "DbSession",
    "UserServiceDep",
    "get_client_context",
    "get_current_user",
    "get_optional_user",
    "require_admin",
    "require_instructor",
    "require_role",
]
