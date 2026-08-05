"""Authentication endpoints.

Token transport
---------------
The access token is returned in the JSON body and held in browser memory only.
The refresh token is written to an httpOnly, SameSite cookie scoped to
`/api/v1/auth`, so it is never readable by JavaScript and is not attached to
ordinary API calls. The practical consequence: an XSS bug can steal at most a
15-minute access token, not a 30-day session.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Response, status

from app.api.deps import CurrentUser, DbSession, get_client_context
from app.core.config import settings
from app.core.datetime_utils import as_utc
from app.core.exceptions import InvalidToken, NotFoundError
from app.core.rate_limit import email_rule, limiter, login_rule
from app.core.security import hash_refresh_token
from app.schemas.auth import LoginRequest, SessionInfo, TokenResponse
from app.schemas.common import ErrorResponse, MessageResponse
from app.schemas.user import PasswordChange, UserCreate, UserRead
from app.schemas.verification import (
    EmailRequest,
    PasswordResetConfirm,
    TokenSubmission,
)
from app.services.auth_service import AuthService, ClientContext, IssuedTokens
from app.services.email_service import EmailService
from app.services.verification_service import VerificationService

router = APIRouter(prefix="/auth", tags=["Authentication"])

ClientContextDep = Annotated[ClientContext, Depends(get_client_context)]
RefreshCookie = Annotated[str | None, Cookie(alias=settings.REFRESH_COOKIE_NAME)]

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


def _set_refresh_cookie(response: Response, tokens: IssuedTokens) -> None:
    """Attach the rotated refresh token as an httpOnly cookie."""
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=tokens.refresh_token,
        max_age=settings.REFRESH_TOKEN_TTL_DAYS * 24 * 60 * 60,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.REFRESH_COOKIE_SAMESITE,
    )


def _token_response(tokens: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        expires_in=tokens.expires_in,
        user=UserRead.model_validate(tokens.user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Create an account",
)
async def register(
    payload: UserCreate,
    response: Response,
    session: DbSession,
    context: ClientContextDep,
) -> TokenResponse:
    """Register a new learner and open a session immediately.

    A verification email is sent, but the account is usable straight away —
    blocking access until a mailbox round trip completes would abandon users at
    the point of highest intent. Verification gates certificates, not learning.
    """
    tokens = await AuthService(session).register(payload, context)
    _set_refresh_cookie(response, tokens)
    await VerificationService(session).send_verification_email(tokens.user)
    return _token_response(tokens)


@router.post(
    "/login",
    response_model=TokenResponse,
    responses=_ERRORS,
    summary="Exchange credentials for tokens",
)
async def login(
    payload: LoginRequest,
    response: Response,
    session: DbSession,
    context: ClientContextDep,
) -> TokenResponse:
    # Throttled per email address to slow online password guessing. Keyed on the
    # address rather than the IP so an attacker rotating through proxies still
    # hits one shared budget for the account they are targeting.
    limiter.check(f"login:{payload.email}", login_rule())

    tokens = await AuthService(session).authenticate(payload.email, payload.password, context)
    _set_refresh_cookie(response, tokens)
    return _token_response(tokens)


@router.post(
    "/refresh",
    response_model=TokenResponse,
    responses=_ERRORS,
    summary="Rotate the refresh token and issue a new access token",
)
async def refresh(
    response: Response,
    session: DbSession,
    context: ClientContextDep,
    refresh_token: RefreshCookie = None,
) -> TokenResponse:
    """Silently extend the session.

    Called by the frontend on page load and whenever an access token expires.
    """
    if not refresh_token:
        raise InvalidToken("No refresh token was supplied.")
    try:
        tokens = await AuthService(session).refresh(refresh_token, context)
    except InvalidToken:
        # The cookie is useless — remove it so the browser stops replaying it.
        _clear_refresh_cookie(response)
        raise
    _set_refresh_cookie(response, tokens)
    return _token_response(tokens)


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Revoke the current session",
)
async def logout(
    response: Response,
    session: DbSession,
    refresh_token: RefreshCookie = None,
) -> MessageResponse:
    """Idempotent: succeeds whether or not a valid session exists."""
    await AuthService(session).logout(refresh_token)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Signed out successfully.")


@router.post(
    "/logout-all",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Revoke every session for the current user",
)
async def logout_all(
    response: Response,
    session: DbSession,
    user: CurrentUser,
) -> MessageResponse:
    count = await AuthService(session).logout_everywhere(user)
    _clear_refresh_cookie(response)
    return MessageResponse(message=f"Signed out of {count} session(s).")


@router.get(
    "/me",
    response_model=UserRead,
    responses=_ERRORS,
    summary="Get the authenticated user",
)
async def read_current_user(user: CurrentUser) -> UserRead:
    return UserRead.model_validate(user)


@router.get(
    "/sessions",
    response_model=list[SessionInfo],
    responses=_ERRORS,
    summary="List active sessions",
)
async def list_sessions(
    session: DbSession,
    user: CurrentUser,
    refresh_token: RefreshCookie = None,
) -> list[SessionInfo]:
    """Show every device holding a live refresh token.

    `isCurrent` lets the UI mark "this device", so a user revoking others does
    not sign themselves out by mistake.
    """
    service = AuthService(session)
    current_hash = hash_refresh_token(refresh_token) if refresh_token else None
    tokens = await service.refresh_tokens.list_active_for_user(user.id)

    return [
        SessionInfo(
            id=str(token.id),
            user_agent=token.user_agent,
            ip_address=token.ip_address,
            issued_at=as_utc(token.issued_at).isoformat(),
            expires_at=as_utc(token.expires_at).isoformat(),
            is_current=token.token_hash == current_hash,
        )
        for token in tokens
    ]


@router.post(
    "/change-password",
    response_model=TokenResponse,
    responses=_ERRORS,
    summary="Change password and re-establish the session",
)
async def change_password(
    payload: PasswordChange,
    response: Response,
    session: DbSession,
    user: CurrentUser,
    context: ClientContextDep,
) -> TokenResponse:
    """All other sessions are revoked as a side effect."""
    tokens = await AuthService(session).change_password(
        user, payload.current_password, payload.new_password, context
    )
    _set_refresh_cookie(response, tokens)
    await EmailService().send_password_changed_notice(to=user.email, name=user.display_name)
    return _token_response(tokens)


@router.delete(
    "/sessions/{session_id}",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Revoke one session",
)
async def revoke_session(
    session_id: uuid.UUID,
    session: DbSession,
    user: CurrentUser,
) -> MessageResponse:
    """Sign one device out.

    Revokes the whole token family, not just the row: a family shares one
    login, so leaving its siblings alive would let that device refresh straight
    back in.
    """
    service = AuthService(session)
    stored = await service.refresh_tokens.get(session_id)

    # Ownership check before existence disclosure — otherwise this endpoint
    # reports whether an arbitrary session ID exists.
    if stored is None or stored.user_id != user.id:
        raise NotFoundError("Session not found.")

    await service.refresh_tokens.revoke_family(stored.family_id)
    await session.commit()
    return MessageResponse(message="Session revoked.")


# --------------------------------------------------------------------------- #
# Email verification
# --------------------------------------------------------------------------- #
@router.post(
    "/verify-email",
    response_model=UserRead,
    responses=_ERRORS,
    summary="Confirm an email address using a token from the emailed link",
)
async def verify_email(payload: TokenSubmission, session: DbSession) -> UserRead:
    """Deliberately unauthenticated: the token itself is the proof.

    Requiring a login would strand anyone opening the link in a browser where
    they are not signed in.
    """
    user = await VerificationService(session).verify_email(payload.token)
    return UserRead.model_validate(user)


@router.post(
    "/resend-verification",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Send a fresh verification email",
)
async def resend_verification(
    session: DbSession,
    user: CurrentUser,
) -> MessageResponse:
    """Authenticated, so the address is known and cannot be probed."""
    limiter.check(f"verify:{user.id}", email_rule())
    await VerificationService(session).send_verification_email(user)
    return MessageResponse(
        message="If your address still needs confirming, a new link is on its way."
    )


# --------------------------------------------------------------------------- #
# Password reset
# --------------------------------------------------------------------------- #
@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Request a password reset link",
)
async def forgot_password(payload: EmailRequest, session: DbSession) -> MessageResponse:
    """Always reports success.

    Saying "no account with that email" would turn this endpoint into a free
    account-existence oracle, and it needs no credentials to query.
    """
    limiter.check(f"reset:{payload.email}", email_rule())
    await VerificationService(session).request_password_reset(payload.email)
    return MessageResponse(message="If that address has an account, a reset link is on its way.")


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Set a new password using a reset token",
)
async def reset_password(
    payload: PasswordResetConfirm,
    response: Response,
    session: DbSession,
) -> MessageResponse:
    """Consumes the token and signs every device out.

    No session is opened here: after a reset the user signs in with the new
    password, which confirms they know it.
    """
    await VerificationService(session).reset_password(payload.token, payload.new_password)
    _clear_refresh_cookie(response)
    return MessageResponse(message="Your password has been reset. You can now sign in.")
