"""Domain exceptions and their HTTP translation.

Services raise semantic exceptions (`EmailAlreadyRegistered`) instead of
`HTTPException`, so the domain layer stays framework-agnostic and unit-testable.
A single set of handlers registered in `app.main` maps them to RFC-9457-style
JSON problem responses.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    """Base class for all expected, handled application errors."""

    status_code: int = 400
    code: str = "app_error"
    message: str = "An unexpected application error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.__class__.message
        self.details = details or {}
        super().__init__(self.message)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.details:
            payload["details"] = self.details
        return {"error": payload}


# ---- 400 / 409 -------------------------------------------------------------
class ValidationError(AppError):
    status_code = 422
    code = "validation_error"
    message = "The submitted data is invalid."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "The resource already exists."


class EmailAlreadyRegistered(ConflictError):
    code = "email_already_registered"
    message = "An account with this email address already exists."


class UsernameAlreadyTaken(ConflictError):
    code = "username_already_taken"
    message = "This username is already taken."


class WeakPasswordError(ValidationError):
    code = "weak_password"
    message = "The password does not meet the minimum security requirements."


# ---- 401 / 403 -------------------------------------------------------------
class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_failed"
    message = "Authentication failed."


class InvalidCredentials(AuthenticationError):
    code = "invalid_credentials"
    message = "Incorrect email or password."


class InvalidToken(AuthenticationError):
    code = "invalid_token"
    message = "The provided token is invalid or has expired."


class InactiveAccount(AuthenticationError):
    status_code = 403
    code = "inactive_account"
    message = "This account has been deactivated."


class PermissionDenied(AppError):
    status_code = 403
    code = "permission_denied"
    message = "You do not have permission to perform this action."


# ---- 404 -------------------------------------------------------------------
class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "The requested resource was not found."


class UserNotFound(NotFoundError):
    code = "user_not_found"
    message = "User not found."


# ---- 429 -------------------------------------------------------------------
class RateLimitExceeded(AppError):
    status_code = 429
    code = "rate_limit_exceeded"
    message = "Too many attempts. Please try again later."
