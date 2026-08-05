"""Tests for email verification and password reset."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.services.email_service import Email, EmailBackend

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"
VERIFY = "/api/v1/auth/verify-email"
RESEND = "/api/v1/auth/resend-verification"
FORGOT = "/api/v1/auth/forgot-password"
RESET = "/api/v1/auth/reset-password"


class CapturingBackend(EmailBackend):
    """Collects messages so tests can read the token out of a link."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, message: Email) -> None:
        self.sent.append(message)

    def token_from_last(self) -> str:
        """Extract the token query parameter from the most recent link."""
        assert self.sent, "no email was sent"
        body = self.sent[-1].text_body
        marker = "token="
        start = body.index(marker) + len(marker)
        end = start
        while end < len(body) and body[end] not in " \n\r\t":
            end += 1
        return body[start:end]


@pytest.fixture
def mailbox(monkeypatch: pytest.MonkeyPatch) -> CapturingBackend:
    """Swap the email backend for a capturing one."""
    backend = CapturingBackend()
    monkeypatch.setattr("app.services.email_service._build_backend", lambda: backend)
    return backend


class TestEmailVerification:
    async def test_registration_sends_a_verification_email(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)

        assert len(mailbox.sent) == 1
        assert mailbox.sent[0].to == user_payload["email"]
        assert "confirm" in mailbox.sent[0].subject.lower()

    async def test_accounts_start_unverified(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        response = await client.post(REGISTER, json=user_payload)
        assert response.json()["user"]["isEmailVerified"] is False

    async def test_the_emailed_token_verifies_the_address(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)

        response = await client.post(VERIFY, json={"token": mailbox.token_from_last()})

        assert response.status_code == 200
        assert response.json()["isEmailVerified"] is True

    async def test_verification_needs_no_login(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        """The link must work in a browser where the user is not signed in."""
        await client.post(REGISTER, json=user_payload)
        token = mailbox.token_from_last()
        client.headers.pop("Authorization", None)

        assert (await client.post(VERIFY, json={"token": token})).status_code == 200

    async def test_a_token_cannot_be_reused(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        token = mailbox.token_from_last()

        assert (await client.post(VERIFY, json={"token": token})).status_code == 200
        replay = await client.post(VERIFY, json={"token": token})

        assert replay.status_code == 401
        assert replay.json()["error"]["code"] == "invalid_token"

    async def test_an_unknown_token_is_rejected(self, client: AsyncClient) -> None:
        response = await client.post(VERIFY, json={"token": "x" * 40})
        assert response.status_code == 401

    async def test_reissuing_invalidates_the_previous_link(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        """Old verification links must die when a new one is issued."""
        register = await client.post(REGISTER, json=user_payload)
        first_token = mailbox.token_from_last()
        client.headers["Authorization"] = f"Bearer {register.json()['accessToken']}"

        await client.post(RESEND)
        second_token = mailbox.token_from_last()
        assert first_token != second_token

        assert (await client.post(VERIFY, json={"token": first_token})).status_code == 401
        assert (await client.post(VERIFY, json={"token": second_token})).status_code == 200

    async def test_resend_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.post(RESEND)).status_code == 401


class TestPasswordReset:
    async def test_reset_email_is_sent_for_a_known_address(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        mailbox.sent.clear()

        response = await client.post(FORGOT, json={"email": user_payload["email"]})

        assert response.status_code == 200
        assert len(mailbox.sent) == 1
        assert "reset" in mailbox.sent[0].subject.lower()

    async def test_unknown_addresses_get_the_same_response(
        self, client: AsyncClient, mailbox: CapturingBackend
    ) -> None:
        """Account enumeration guard — the reply must not differ."""
        response = await client.post(FORGOT, json={"email": "nobody@example.com"})

        assert response.status_code == 200
        assert mailbox.sent == []

    async def test_the_reset_token_sets_a_new_password(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        await client.post(FORGOT, json={"email": user_payload["email"]})
        token = mailbox.token_from_last()

        response = await client.post(RESET, json={"token": token, "newPassword": "CompletelyNew99"})
        assert response.status_code == 200

        old = await client.post(
            LOGIN, json={"email": user_payload["email"], "password": user_payload["password"]}
        )
        assert old.status_code == 401

        new = await client.post(
            LOGIN, json={"email": user_payload["email"], "password": "CompletelyNew99"}
        )
        assert new.status_code == 200

    async def test_a_reset_token_is_single_use(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        await client.post(FORGOT, json={"email": user_payload["email"]})
        token = mailbox.token_from_last()

        assert (
            await client.post(RESET, json={"token": token, "newPassword": "CompletelyNew99"})
        ).status_code == 200
        replay = await client.post(RESET, json={"token": token, "newPassword": "AnotherOne123"})
        assert replay.status_code == 401

    async def test_reset_revokes_every_existing_session(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        """Whoever triggered the reset must not keep a live session."""
        from app.core.config import settings

        await client.post(REGISTER, json=user_payload)
        pre_reset_refresh = client.cookies[settings.REFRESH_COOKIE_NAME]

        await client.post(FORGOT, json={"email": user_payload["email"]})
        await client.post(
            RESET,
            json={"token": mailbox.token_from_last(), "newPassword": "CompletelyNew99"},
        )

        replay = await client.post(
            "/api/v1/auth/refresh",
            cookies={settings.REFRESH_COOKIE_NAME: pre_reset_refresh},
        )
        assert replay.status_code == 401

    async def test_reset_also_confirms_the_email(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        """Receiving the link proves control of the mailbox."""
        await client.post(REGISTER, json=user_payload)
        await client.post(FORGOT, json={"email": user_payload["email"]})
        await client.post(
            RESET,
            json={"token": mailbox.token_from_last(), "newPassword": "CompletelyNew99"},
        )

        login = await client.post(
            LOGIN, json={"email": user_payload["email"], "password": "CompletelyNew99"}
        )
        assert login.json()["user"]["isEmailVerified"] is True

    async def test_a_weak_new_password_is_rejected(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        await client.post(REGISTER, json=user_payload)
        await client.post(FORGOT, json={"email": user_payload["email"]})

        response = await client.post(
            RESET, json={"token": mailbox.token_from_last(), "newPassword": "weak"}
        )
        assert response.status_code == 422

    async def test_a_verification_token_cannot_reset_a_password(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        """Purposes must not be interchangeable."""
        await client.post(REGISTER, json=user_payload)
        verification_token = mailbox.token_from_last()

        response = await client.post(
            RESET, json={"token": verification_token, "newPassword": "CompletelyNew99"}
        )
        assert response.status_code == 401


class TestRateLimiting:
    async def test_repeated_reset_requests_are_throttled(
        self, client: AsyncClient, mailbox: CapturingBackend
    ) -> None:
        from app.core.config import settings

        payload = {"email": "target@example.com"}
        for _ in range(settings.RATE_LIMIT_EMAIL_PER_HOUR):
            assert (await client.post(FORGOT, json=payload)).status_code == 200

        blocked = await client.post(FORGOT, json=payload)
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limit_exceeded"

    async def test_repeated_failed_logins_are_throttled(
        self, client: AsyncClient, user_payload: dict[str, str], mailbox: CapturingBackend
    ) -> None:
        from app.core.config import settings

        await client.post(REGISTER, json=user_payload)
        attempt = {"email": user_payload["email"], "password": "WrongPassword1"}

        for _ in range(settings.RATE_LIMIT_LOGIN_PER_15_MIN):
            await client.post(LOGIN, json=attempt)

        blocked = await client.post(LOGIN, json=attempt)
        assert blocked.status_code == 429

    async def test_the_limit_is_per_address(
        self, client: AsyncClient, mailbox: CapturingBackend
    ) -> None:
        """One throttled account must not lock out everyone else."""
        from app.core.config import settings

        for _ in range(settings.RATE_LIMIT_EMAIL_PER_HOUR + 1):
            await client.post(FORGOT, json={"email": "first@example.com"})

        other = await client.post(FORGOT, json={"email": "second@example.com"})
        assert other.status_code == 200
