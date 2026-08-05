"""Integration tests for the authentication endpoints."""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import settings

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
REFRESH = "/api/v1/auth/refresh"
LOGOUT = "/api/v1/auth/logout"
ME = "/api/v1/auth/me"
CHANGE_PASSWORD = "/api/v1/auth/change-password"


class TestRegistration:
    async def test_registers_and_returns_a_session(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        response = await client.post(REGISTER, json=user_payload)

        assert response.status_code == 201
        body = response.json()
        assert body["tokenType"] == "bearer"
        assert body["expiresIn"] > 0
        assert body["user"]["email"] == user_payload["email"]
        assert body["user"]["username"] == user_payload["username"]
        # The password hash must never appear in a response.
        assert "hashed_password" not in body["user"]
        assert "password" not in body["user"]

    async def test_sets_httponly_refresh_cookie(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        response = await client.post(REGISTER, json=user_payload)

        cookie_header = response.headers.get("set-cookie", "")
        assert settings.REFRESH_COOKIE_NAME in cookie_header
        assert "HttpOnly" in cookie_header
        # The refresh token itself must not be in the JSON body.
        assert "refreshToken" not in response.json()

    async def test_first_account_becomes_administrator(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        """Bootstrap rule: a fresh instance must be administrable."""
        response = await client.post(REGISTER, json=user_payload)
        assert response.json()["user"]["role"] == "admin"

    async def test_second_account_is_a_student(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        second = await client.post(
            REGISTER,
            json={**user_payload, "email": "second@example.com", "username": "second"},
        )
        assert second.json()["user"]["role"] == "student"

    async def test_duplicate_email_is_rejected(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        response = await client.post(REGISTER, json={**user_payload, "username": "other"})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "email_already_registered"

    async def test_duplicate_username_is_rejected(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        response = await client.post(REGISTER, json={**user_payload, "email": "other@example.com"})

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "username_already_taken"

    async def test_email_is_stored_case_insensitively(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json={**user_payload, "email": "Learner@Example.COM"})
        response = await client.post(
            LOGIN, json={"email": "learner@example.com", "password": user_payload["password"]}
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "password",
        ["short1", "alllettersnodigits", "1234567890123", "aB1"],
        ids=["too-short", "no-digit", "no-letter", "far-too-short"],
    )
    async def test_weak_passwords_are_rejected(
        self, client: AsyncClient, user_payload: dict[str, str], password: str
    ) -> None:
        response = await client.post(REGISTER, json={**user_payload, "password": password})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    @pytest.mark.parametrize(
        "username",
        ["ab", "has spaces", "sym!bols", "admin", "root"],
        ids=["too-short", "spaces", "symbols", "reserved-admin", "reserved-root"],
    )
    async def test_invalid_usernames_are_rejected(
        self, client: AsyncClient, user_payload: dict[str, str], username: str
    ) -> None:
        response = await client.post(REGISTER, json={**user_payload, "username": username})
        assert response.status_code == 422


class TestLogin:
    async def test_valid_credentials_succeed(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        response = await client.post(
            LOGIN, json={"email": user_payload["email"], "password": user_payload["password"]}
        )

        assert response.status_code == 200
        assert response.json()["accessToken"]

    async def test_wrong_password_is_rejected(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        response = await client.post(
            LOGIN, json={"email": user_payload["email"], "password": "WrongPassword1"}
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    async def test_unknown_email_gives_the_same_error(self, client: AsyncClient) -> None:
        """Account enumeration guard: the message must not distinguish the case."""
        response = await client.post(
            LOGIN, json={"email": "nobody@example.com", "password": "Subnetting2024"}
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"


class TestRefreshRotation:
    async def test_refresh_issues_a_new_access_token(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        response = await client.post(REFRESH)

        assert response.status_code == 200
        assert response.json()["accessToken"]

    async def test_refresh_rotates_the_cookie(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        original = client.cookies[settings.REFRESH_COOKIE_NAME]

        await client.post(REFRESH)
        rotated = client.cookies[settings.REFRESH_COOKIE_NAME]

        assert rotated != original

    async def test_reusing_a_rotated_token_revokes_the_family(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        """The core reuse-detection guarantee.

        A stolen refresh token replayed after the legitimate client has already
        rotated it must invalidate the whole session, not just that one token.
        """
        await client.post(REGISTER, json=user_payload)
        stolen = client.cookies[settings.REFRESH_COOKIE_NAME]

        # Legitimate client rotates, invalidating `stolen`.
        await client.post(REFRESH)
        live_token = client.cookies[settings.REFRESH_COOKIE_NAME]

        # Attacker replays the stolen token.
        replay = await client.post(REFRESH, cookies={settings.REFRESH_COOKIE_NAME: stolen})
        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "invalid_token"

        # The legitimate token is now dead too — the family was burned.
        aftermath = await client.post(REFRESH, cookies={settings.REFRESH_COOKIE_NAME: live_token})
        assert aftermath.status_code == 401

    async def test_refresh_without_a_cookie_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(REFRESH)
        assert response.status_code == 401

    async def test_garbage_cookie_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(
            REFRESH, cookies={settings.REFRESH_COOKIE_NAME: "not-a-real-token"}
        )
        assert response.status_code == 401


class TestLogout:
    async def test_logout_invalidates_the_session(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        token = client.cookies[settings.REFRESH_COOKIE_NAME]

        assert (await client.post(LOGOUT)).status_code == 200

        replay = await client.post(REFRESH, cookies={settings.REFRESH_COOKIE_NAME: token})
        assert replay.status_code == 401

    async def test_logout_is_idempotent(self, client: AsyncClient) -> None:
        """Logging out with no session must still succeed."""
        assert (await client.post(LOGOUT)).status_code == 200


class TestCurrentUser:
    async def test_returns_the_authenticated_user(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get(ME)

        assert response.status_code == 200
        assert response.json()["username"] == "learner"

    async def test_includes_initialised_stats(self, authed_client: AsyncClient) -> None:
        """Every account gets a stats row at registration."""
        stats = response_stats(await authed_client.get(ME))
        assert stats["totalXp"] == 0
        assert stats["level"] == 1

    async def test_requires_a_token(self, client: AsyncClient) -> None:
        response = await client.get(ME)
        assert response.status_code == 401

    async def test_rejects_a_malformed_token(self, client: AsyncClient) -> None:
        client.headers["Authorization"] = "Bearer not.a.jwt"
        response = await client.get(ME)
        assert response.status_code == 401


class TestChangePassword:
    async def test_changes_the_password(
        self, authed_client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        response = await authed_client.post(
            CHANGE_PASSWORD,
            json={
                "current_password": user_payload["password"],
                "new_password": "BrandNewPass99",
            },
        )
        assert response.status_code == 200

        # The old password no longer works.
        old = await authed_client.post(
            LOGIN, json={"email": user_payload["email"], "password": user_payload["password"]}
        )
        assert old.status_code == 401

        # The new one does.
        new = await authed_client.post(
            LOGIN, json={"email": user_payload["email"], "password": "BrandNewPass99"}
        )
        assert new.status_code == 200

    async def test_wrong_current_password_is_rejected(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            CHANGE_PASSWORD,
            json={"current_password": "NotMyPassword1", "new_password": "BrandNewPass99"},
        )
        assert response.status_code == 401

    async def test_weak_new_password_is_rejected(
        self, authed_client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        response = await authed_client.post(
            CHANGE_PASSWORD,
            json={"current_password": user_payload["password"], "new_password": "weak"},
        )
        assert response.status_code == 422


class TestAuthorization:
    async def test_student_cannot_list_users(self, client: AsyncClient) -> None:
        """Role guard: the admin-only endpoint must reject a student."""
        # The first account is auto-promoted to admin, so register it first and
        # then work as the second (student) account.
        await client.post(
            REGISTER,
            json={
                "email": "admin@example.com",
                "username": "theadmin",
                "password": "AdminPass2024",
            },
        )
        student = await client.post(
            REGISTER,
            json={
                "email": "student@example.com",
                "username": "student1",
                "password": "StudentPass24",
            },
        )
        client.headers["Authorization"] = f"Bearer {student.json()['accessToken']}"

        response = await client.get("/api/v1/users")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"

    async def test_admin_can_list_users(self, authed_client: AsyncClient) -> None:
        """The bootstrap admin has access."""
        response = await authed_client.get("/api/v1/users")
        assert response.status_code == 200
        assert response.json()["total"] == 1


def response_stats(response: Any) -> dict[str, Any]:
    """Pull the nested stats object out of a user response."""
    stats = response.json()["stats"]
    assert stats is not None, "user response should embed stats"
    return stats
