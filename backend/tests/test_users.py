"""Tests for profile management, sessions, and the progress endpoints."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.config import settings

ME = "/api/v1/users/me"
PROGRESS = "/api/v1/users/me/progress"
ACTIVITY = "/api/v1/users/me/activity"
DEACTIVATE = "/api/v1/users/me/deactivate"
SESSIONS = "/api/v1/auth/sessions"
LOGIN = "/api/v1/auth/login"
REGISTER = "/api/v1/auth/register"


class TestProfile:
    async def test_updates_the_supplied_fields(self, authed_client: AsyncClient) -> None:
        response = await authed_client.patch(
            ME, json={"fullName": "Ada Lovelace", "bio": "Learning OSPF.", "country": "GB"}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["fullName"] == "Ada Lovelace"
        assert body["bio"] == "Learning OSPF."
        assert body["country"] == "GB"

    async def test_omitted_fields_are_left_alone(self, authed_client: AsyncClient) -> None:
        """A partial update must not blank out what it does not mention."""
        await authed_client.patch(ME, json={"fullName": "Ada Lovelace", "bio": "Original bio."})
        response = await authed_client.patch(ME, json={"country": "GB"})

        assert response.json()["bio"] == "Original bio."
        assert response.json()["fullName"] == "Ada Lovelace"

    async def test_accepts_a_valid_timezone(self, authed_client: AsyncClient) -> None:
        response = await authed_client.patch(ME, json={"timezone": "Europe/London"})
        assert response.status_code == 200
        assert response.json()["timezone"] == "Europe/London"

    async def test_rejects_an_unknown_timezone(self, authed_client: AsyncClient) -> None:
        """An invalid zone would silently miscount that learner's streaks."""
        response = await authed_client.patch(ME, json={"timezone": "Mars/Olympus_Mons"})

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.patch(ME, json={"fullName": "x"})).status_code == 401

    async def test_public_profile_hides_private_fields(self, authed_client: AsyncClient) -> None:
        me = (await authed_client.get(ME)).json()
        response = await authed_client.get(f"/api/v1/users/{me['id']}")

        assert response.status_code == 200
        body = response.json()
        assert body["username"] == me["username"]
        assert "email" not in body
        assert "isActive" not in body
        assert "role" not in body


class TestProgressEndpoints:
    async def test_new_account_starts_empty(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get(PROGRESS)

        assert response.status_code == 200
        body = response.json()
        assert body["totalXp"] == 0
        assert body["level"]["level"] == 1
        assert body["currentStreakDays"] == 0
        assert body["recentXp"] == []

    async def test_level_block_is_computed_server_side(self, authed_client: AsyncClient) -> None:
        """The client must never reimplement the level curve."""
        body = (await authed_client.get(PROGRESS)).json()["level"]

        assert set(body) >= {
            "level",
            "totalXp",
            "nextLevelXp",
            "xpIntoLevel",
            "percentToNextLevel",
            "isMaxLevel",
        }

    async def test_activity_ping_starts_a_streak(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(ACTIVITY, json={"studySeconds": 120})

        assert response.status_code == 200
        body = response.json()
        assert body["currentStreakDays"] == 1
        assert body["totalStudySeconds"] == 120

    async def test_study_seconds_are_capped(self, authed_client: AsyncClient) -> None:
        """A tampered client must not be able to inflate study totals."""
        response = await authed_client.post(ACTIVITY, json={"studySeconds": 999_999})

        assert response.status_code == 422
        assert "studySeconds" in response.json()["error"]["details"]["fields"]

    async def test_negative_study_seconds_are_rejected(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(ACTIVITY, json={"studySeconds": -60})
        assert response.status_code == 422

    async def test_progress_requires_authentication(self, client: AsyncClient) -> None:
        assert (await client.get(PROGRESS)).status_code == 401


class TestSessions:
    async def test_lists_the_current_session(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get(SESSIONS)

        assert response.status_code == 200
        sessions = response.json()
        assert len(sessions) == 1
        assert sessions[0]["isCurrent"] is True

    async def test_a_second_login_appears_as_another_session(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        registration = await client.post(REGISTER, json=user_payload)
        client.headers["Authorization"] = f"Bearer {registration.json()['accessToken']}"

        # A separate client stands in for a second device.
        await client.post(
            LOGIN,
            json={"email": user_payload["email"], "password": user_payload["password"]},
        )

        sessions = (await client.get(SESSIONS)).json()
        assert len(sessions) == 2

    async def test_revoking_a_session_removes_it(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        registration = await client.post(REGISTER, json=user_payload)
        client.headers["Authorization"] = f"Bearer {registration.json()['accessToken']}"
        await client.post(
            LOGIN,
            json={"email": user_payload["email"], "password": user_payload["password"]},
        )

        sessions = (await client.get(SESSIONS)).json()
        target = next(item for item in sessions if not item["isCurrent"])

        response = await client.delete(f"{SESSIONS}/{target['id']}")
        assert response.status_code == 200

        remaining = (await client.get(SESSIONS)).json()
        assert target["id"] not in [item["id"] for item in remaining]

    async def test_cannot_revoke_another_users_session(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        """Ownership is checked before existence is disclosed."""
        await client.post(REGISTER, json=user_payload)
        victim_sessions = (
            await client.get(
                SESSIONS,
                headers={
                    "Authorization": f"Bearer {(await client.post(LOGIN, json={'email': user_payload['email'], 'password': user_payload['password']})).json()['accessToken']}"
                },
            )
        ).json()
        victim_session_id = victim_sessions[0]["id"]

        attacker = await client.post(
            REGISTER,
            json={
                "email": "attacker@example.com",
                "username": "attacker",
                "password": "AttackerPass24",
            },
        )
        client.headers["Authorization"] = f"Bearer {attacker.json()['accessToken']}"

        response = await client.delete(f"{SESSIONS}/{victim_session_id}")
        assert response.status_code == 404


class TestDeactivation:
    async def test_deactivation_blocks_further_login(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        registration = await client.post(REGISTER, json=user_payload)
        client.headers["Authorization"] = f"Bearer {registration.json()['accessToken']}"

        assert (await client.post(DEACTIVATE)).status_code == 200

        login = await client.post(
            LOGIN,
            json={"email": user_payload["email"], "password": user_payload["password"]},
        )
        assert login.status_code == 403
        assert login.json()["error"]["code"] == "inactive_account"

    async def test_deactivation_kills_the_live_session(
        self, client: AsyncClient, user_payload: dict[str, str]
    ) -> None:
        registration = await client.post(REGISTER, json=user_payload)
        client.headers["Authorization"] = f"Bearer {registration.json()['accessToken']}"
        refresh_token = client.cookies[settings.REFRESH_COOKIE_NAME]

        await client.post(DEACTIVATE)

        replay = await client.post(
            "/api/v1/auth/refresh",
            cookies={settings.REFRESH_COOKIE_NAME: refresh_token},
        )
        assert replay.status_code in (401, 403)
