"""Authentication request/response schemas."""

from __future__ import annotations

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel
from app.schemas.user import UserRead


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.lower()


class TokenResponse(APIModel):
    """Issued after login, registration, or refresh.

    Only the access token appears in the body. The refresh token is set as an
    httpOnly cookie by the endpoint and is never readable from JavaScript,
    which is what makes an XSS bug non-fatal to the session.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds.")
    user: UserRead


class SessionInfo(APIModel):
    """A device with an active refresh token, for the security settings page."""

    id: str
    user_agent: str | None
    ip_address: str | None
    issued_at: str
    expires_at: str
    is_current: bool
