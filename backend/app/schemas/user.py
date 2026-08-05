"""User-facing schemas."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.core.config import settings
from app.models.enums import UserRole
from app.schemas.common import APIModel

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{3,32}$")

# Rejected outright so nobody can impersonate a platform account.
RESERVED_USERNAMES = frozenset(
    {"admin", "administrator", "root", "system", "support", "api", "null", "undefined"}
)


def validate_password_strength(password: str) -> str:
    """Enforce the password policy.

    Length is the dominant factor in resistance to offline cracking, so the
    floor is high (10 by default) and character-class rules stay light: one
    letter and one digit. Requiring symbols measurably pushes users toward
    predictable substitutions without adding real entropy.
    """
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        raise ValueError(
            f"Password must be at least {settings.PASSWORD_MIN_LENGTH} characters long."
        )
    if len(password) > 128:
        # Argon2 has no practical input limit, but an unbounded field is a
        # cheap denial-of-service vector against a memory-hard hash.
        raise ValueError("Password must be at most 128 characters long.")
    if not re.search(r"[A-Za-z]", password):
        raise ValueError("Password must contain at least one letter.")
    if not re.search(r"\d", password):
        raise ValueError("Password must contain at least one digit.")
    return password


class UserBase(APIModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=32)
    full_name: str | None = Field(default=None, max_length=120)


class UserCreate(UserBase):
    """Registration payload."""

    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _normalise_email(cls, value: str) -> str:
        # Stored lowercase so uniqueness is case-insensitive on both dialects.
        return value.lower()

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        if not USERNAME_PATTERN.match(value):
            raise ValueError("Username may contain only letters, numbers, hyphens and underscores.")
        if value.lower() in RESERVED_USERNAMES:
            raise ValueError("This username is reserved.")
        return value

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UserUpdate(APIModel):
    """Self-service profile edit. Every field is optional."""

    full_name: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=2000)
    avatar_url: str | None = Field(default=None, max_length=512)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    timezone: str | None = Field(default=None, max_length=64)


class PasswordChange(APIModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)

    @field_validator("new_password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_password_strength(value)


class UserStatsRead(APIModel):
    total_xp: int
    level: int
    lessons_completed: int
    courses_completed: int
    labs_completed: int
    quizzes_passed: int
    total_study_seconds: int
    current_streak_days: int
    longest_streak_days: int


class UserRead(APIModel):
    """Public-facing representation of the authenticated user."""

    id: uuid.UUID
    email: EmailStr
    username: str
    full_name: str | None
    avatar_url: str | None
    bio: str | None
    country: str | None
    timezone: str
    role: UserRole
    is_active: bool
    is_email_verified: bool
    created_at: datetime
    last_login_at: datetime | None
    stats: UserStatsRead | None = None


class UserPublic(APIModel):
    """Reduced projection used in leaderboards and instructor listings.

    Deliberately excludes email and any account-state flags.
    """

    id: uuid.UUID
    username: str
    full_name: str | None
    avatar_url: str | None
    country: str | None
