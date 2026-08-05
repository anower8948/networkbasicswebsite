"""Application configuration.

Settings are loaded from environment variables (and a local `.env` file in
development) exactly once, at import time, via `get_settings()`. Every module
depends on this single source of truth rather than reading `os.environ`
directly, which keeps configuration testable and auditable.
"""

from __future__ import annotations

import secrets
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

Environment = Literal["development", "staging", "production", "test"]


class Settings(BaseSettings):
    """Runtime configuration for the Network Learning Platform API."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Application -------------------------------------------------------
    APP_NAME: str = "Network Learning Platform API"
    API_V1_PREFIX: str = "/api/v1"
    ENVIRONMENT: Environment = "development"
    DEBUG: bool = False

    # ---- Security ----------------------------------------------------------
    # A generated default keeps local development frictionless. Any non-local
    # environment MUST provide an explicit value; see the validator below.
    SECRET_KEY: str = Field(default_factory=lambda: secrets.token_urlsafe(64))
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "network-learning-platform"

    # Refresh tokens travel in an httpOnly cookie; these control its scope.
    REFRESH_COOKIE_NAME: str = "nlp_refresh"
    REFRESH_COOKIE_PATH: str = "/api/v1/auth"
    REFRESH_COOKIE_SECURE: bool = False
    REFRESH_COOKIE_SAMESITE: Literal["lax", "strict", "none"] = "lax"
    REFRESH_COOKIE_DOMAIN: str | None = None

    # ---- Database ----------------------------------------------------------
    # Async driver URLs: sqlite+aiosqlite:// for dev, postgresql+asyncpg:// for prod.
    DATABASE_URL: str = "sqlite+aiosqlite:///./network_learning.db"
    DB_ECHO: bool = False
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # ---- CORS --------------------------------------------------------------
    # `NoDecode` disables pydantic-settings' automatic JSON parsing so the
    # validator below can accept a plain comma-separated string, which is what
    # Azure App Service application settings and Docker `-e` flags provide.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ---- Host and payload limits ------------------------------------------
    # Host header allow-list. `*` accepts anything, which is right behind a
    # trusted reverse proxy that has already matched the host, and wrong when
    # the app is directly reachable — a spoofed Host poisons absolute URLs in
    # password-reset mail.
    ALLOWED_HOSTS: Annotated[list[str], NoDecode] = ["*"]

    # A topology document with 200 devices is a few hundred KB; 4 MB leaves
    # generous headroom while stopping a memory-exhaustion POST.
    MAX_REQUEST_BYTES: int = 4 * 1024 * 1024

    # Responses above this are gzipped. Below ~1 KB compression costs more CPU
    # than it saves bytes.
    GZIP_MIN_BYTES: int = 1024

    # ---- Security headers --------------------------------------------------
    # HSTS is only meaningful over TLS, and sending it from a plain-HTTP dev
    # server would pin localhost to HTTPS in the developer's browser.
    HSTS_ENABLED: bool = False
    HSTS_MAX_AGE_SECONDS: int = 31_536_000  # one year

    # ---- Registration policy ----------------------------------------------
    PASSWORD_MIN_LENGTH: int = 10
    # First account created on an empty instance is promoted to admin. Disable
    # in production once the real admin exists.
    BOOTSTRAP_FIRST_USER_AS_ADMIN: bool = True

    # ---- Single-use tokens -------------------------------------------------
    # Verification links are long-lived because people open mail hours later.
    EMAIL_VERIFICATION_TTL_HOURS: int = 48
    # Reset links are short-lived: the window in which a leaked link is usable
    # should be as small as remains practical.
    PASSWORD_RESET_TTL_MINUTES: int = 30

    # ---- Email -------------------------------------------------------------
    # "console" writes the message to the log — the development default, so no
    # SMTP server is needed to click through the verification flow.
    EMAIL_BACKEND: Literal["console", "smtp"] = "console"
    EMAIL_FROM: str = "Network Learning Platform <no-reply@networklearning.local>"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_USE_TLS: bool = True

    # Base URL used to build links in outbound email. Must be the address the
    # browser reaches, not the API's own origin.
    FRONTEND_URL: str = "http://localhost:5173"

    # ---- Rate limiting -----------------------------------------------------
    # Applied to the endpoints that send mail or accept credentials, which are
    # the ones worth abusing. See `app.core.rate_limit` for the caveats.
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_EMAIL_PER_HOUR: int = 5
    RATE_LIMIT_LOGIN_PER_15_MIN: int = 10

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def _blank_secret_is_no_secret(cls, value: object) -> object:
        """Treat `SECRET_KEY=` as unset rather than as an empty key.

        `.env.example` ships the key blank — it has no business containing a
        real one — and the README says to copy it. Taken literally, that gave
        every fresh checkout a zero-length HMAC key, and PyJWT refuses to sign
        with it: *every* login failed with "HMAC key must not be empty".

        Falling back to the generated default makes `cp .env.example .env` work
        as documented. Production is unaffected: its guard reads the raw
        environment variable and still refuses to start without one.
        """
        if isinstance(value, str) and not value.strip():
            return secrets.token_urlsafe(64)
        return value

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def _split_list(cls, value: object) -> object:
        """Accept a comma-separated string so the value is easy to set in Azure/Docker."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):  # already JSON
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Settings:
        """Refuse to start a production process that is misconfigured.

        Every check here is something that is silently wrong rather than
        obviously broken — the app would run, and the weakness would only show
        up in an incident. Failing at start-up is the whole point: a container
        that will not boot gets noticed; a missing `Secure` flag does not.
        """
        if self.ENVIRONMENT != "production":
            return self

        import os

        problems: list[str] = []

        if not os.environ.get("SECRET_KEY"):
            problems.append(
                "SECRET_KEY must be set explicitly — a generated key would "
                "invalidate every token on restart."
            )
        elif len(self.SECRET_KEY) < 32:
            problems.append("SECRET_KEY must be at least 32 characters.")

        if self.DEBUG:
            problems.append("DEBUG must be false.")
        if not self.REFRESH_COOKIE_SECURE:
            problems.append("REFRESH_COOKIE_SECURE must be true.")
        if not self.HSTS_ENABLED:
            problems.append(
                "HSTS_ENABLED must be true (set it false only when a separate "
                "edge already sends Strict-Transport-Security)."
            )
        if not self.RATE_LIMIT_ENABLED:
            problems.append("RATE_LIMIT_ENABLED must be true.")

        # A localhost origin in production means the allow-list was never
        # configured, which makes CORS decorative.
        local = [
            origin for origin in self.CORS_ORIGINS if "localhost" in origin or "127.0.0.1" in origin
        ]
        if local:
            problems.append(f"CORS_ORIGINS still contains local addresses: {', '.join(local)}.")
        if any(origin == "*" for origin in self.CORS_ORIGINS):
            problems.append("CORS_ORIGINS cannot be '*' while credentials are allowed.")

        if self.is_sqlite:
            problems.append(
                "DATABASE_URL points at SQLite. Production must use PostgreSQL — "
                "SQLite serialises writers and cannot be shared between instances."
            )

        if self.EMAIL_BACKEND == "console":
            problems.append(
                "EMAIL_BACKEND is 'console', so verification and reset mail would "
                "only be written to the log."
            )
        if self.FRONTEND_URL.startswith("http://"):
            problems.append("FRONTEND_URL must be https — it is used to build emailed links.")

        if problems:
            raise ValueError(
                "Refusing to start with ENVIRONMENT=production:\n  - " + "\n  - ".join(problems)
            )
        return self

    @property
    def is_sqlite(self) -> bool:
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings singleton."""
    return Settings()


settings = get_settings()
