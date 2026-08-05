"""Email verification and password reset payloads."""

from __future__ import annotations

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import APIModel
from app.schemas.user import validate_password_strength


class EmailRequest(APIModel):
    """Used by both "forgot password" and "resend verification"."""

    email: EmailStr

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        return value.lower()


class TokenSubmission(APIModel):
    """A token lifted from a verification or reset link."""

    token: str = Field(min_length=16, max_length=256)


class PasswordResetConfirm(APIModel):
    token: str = Field(min_length=16, max_length=256)
    new_password: str = Field(min_length=1, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_password_strength(value)
