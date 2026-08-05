"""Tests for notes, bookmarks, and instructor tooling.

The security property under test throughout: **one learner's annotations are
invisible to another**, and instructor tooling is gated by role rather than by
the UI simply not linking to it.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient

ENROLL = "/api/v1/courses/network-fundamentals/enroll"


async def first_lesson_id(client: AsyncClient) -> str:
    course = await client.get("/api/v1/courses/network-fundamentals")
    lesson: dict[str, Any] = course.json()["modules"][0]["lessons"][0]
    return str(lesson["id"])


async def register(client: AsyncClient, email: str) -> str:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "username": email.split("@")[0],
            "password": "Subnetting2024",
            "fullName": "Someone Else",
        },
    )
    return str(response.json()["accessToken"])


@pytest.mark.usefixtures("seeded_catalog")
class TestNotes:
    async def test_writing_and_listing_a_note(self, authed_client: AsyncClient) -> None:
        lesson_id = await first_lesson_id(authed_client)

        created = await authed_client.post(
            "/api/v1/notes",
            json={"lessonId": lesson_id, "body": "MAC is layer 2.", "blockIndex": 3},
        )

        assert created.status_code == 201
        listed = await authed_client.get(f"/api/v1/notes/lesson/{lesson_id}")
        assert [item["body"] for item in listed.json()] == ["MAC is layer 2."]

    async def test_notes_carry_their_lesson_on_the_all_notes_view(
        self, authed_client: AsyncClient
    ) -> None:
        """Otherwise the page cannot link back to where the note was written."""
        lesson_id = await first_lesson_id(authed_client)
        await authed_client.post(
            "/api/v1/notes", json={"lessonId": lesson_id, "body": "Remember this."}
        )

        response = await authed_client.get("/api/v1/notes")

        entry = response.json()[0]
        assert entry["lessonTitle"]
        assert entry["courseSlug"] == "network-fundamentals"

    async def test_pinned_notes_come_first(self, authed_client: AsyncClient) -> None:
        lesson_id = await first_lesson_id(authed_client)
        await authed_client.post(
            "/api/v1/notes", json={"lessonId": lesson_id, "body": "Ordinary", "blockIndex": 1}
        )
        second = await authed_client.post(
            "/api/v1/notes", json={"lessonId": lesson_id, "body": "Important", "blockIndex": 9}
        )
        await authed_client.patch(f"/api/v1/notes/{second.json()['id']}", json={"isPinned": True})

        listed = await authed_client.get(f"/api/v1/notes/lesson/{lesson_id}")

        assert [item["body"] for item in listed.json()] == ["Important", "Ordinary"]

    async def test_editing_a_note(self, authed_client: AsyncClient) -> None:
        lesson_id = await first_lesson_id(authed_client)
        created = await authed_client.post(
            "/api/v1/notes", json={"lessonId": lesson_id, "body": "Draft"}
        )

        updated = await authed_client.patch(
            f"/api/v1/notes/{created.json()['id']}", json={"body": "Revised"}
        )

        assert updated.json()["body"] == "Revised"

    async def test_deleting_a_note(self, authed_client: AsyncClient) -> None:
        lesson_id = await first_lesson_id(authed_client)
        created = await authed_client.post(
            "/api/v1/notes", json={"lessonId": lesson_id, "body": "Temporary"}
        )

        await authed_client.delete(f"/api/v1/notes/{created.json()['id']}")

        assert (await authed_client.get("/api/v1/notes")).json() == []

    async def test_another_learners_note_is_not_reachable(
        self, authed_client: AsyncClient, client: AsyncClient
    ) -> None:
        lesson_id = await first_lesson_id(authed_client)
        created = await authed_client.post(
            "/api/v1/notes", json={"lessonId": lesson_id, "body": "Private"}
        )
        token = await register(client, "nosy@example.com")

        response = await client.patch(
            f"/api/v1/notes/{created.json()['id']}",
            json={"body": "Tampered"},
            headers={"Authorization": f"Bearer {token}"},
        )

        # 404, not 403: this must not confirm the note exists.
        assert response.status_code == 404

    async def test_notes_require_a_user(self, client: AsyncClient) -> None:
        assert (await client.get("/api/v1/notes")).status_code == 401


@pytest.mark.usefixtures("seeded_catalog")
class TestBookmarks:
    async def test_bookmarking_toggles(self, authed_client: AsyncClient) -> None:
        lesson_id = await first_lesson_id(authed_client)

        added = await authed_client.post("/api/v1/bookmarks", json={"lessonId": lesson_id})
        assert "Bookmarked" in added.json()["message"]
        assert len((await authed_client.get("/api/v1/bookmarks")).json()) == 1

        removed = await authed_client.post("/api/v1/bookmarks", json={"lessonId": lesson_id})
        assert "removed" in removed.json()["message"]
        assert (await authed_client.get("/api/v1/bookmarks")).json() == []

    async def test_a_bookmark_carries_enough_to_link_back(self, authed_client: AsyncClient) -> None:
        lesson_id = await first_lesson_id(authed_client)
        await authed_client.post("/api/v1/bookmarks", json={"lessonId": lesson_id})

        entry = (await authed_client.get("/api/v1/bookmarks")).json()[0]

        assert entry["courseSlug"] == "network-fundamentals"
        assert entry["lessonSlug"]


@pytest.mark.usefixtures("seeded_catalog")
class TestAdminTools:
    """The first registered account becomes the administrator."""

    async def test_analytics_reports_content_performance(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/admin/analytics")

        assert response.status_code == 200
        body = response.json()
        assert body["overview"]["totalUsers"] >= 1
        assert len(body["labs"]) > 0
        assert len(body["courses"]) > 0

    async def test_lab_performance_reports_pass_rate_and_hints(
        self, authed_client: AsyncClient
    ) -> None:
        """The two numbers that tell an author a lab is badly worded."""
        started = await authed_client.post("/api/v1/labs/your-first-lan/attempts")
        attempt_id = started.json()["id"]
        await authed_client.post(
            f"/api/v1/labs/attempts/{attempt_id}/hint", json={"objectiveId": "address-pc1"}
        )
        await authed_client.post(f"/api/v1/labs/attempts/{attempt_id}/submit")

        response = await authed_client.get("/api/v1/admin/analytics")

        lab = next(item for item in response.json()["labs"] if item["slug"] == "your-first-lan")
        assert lab["attempts"] == 1
        assert lab["passRate"] == 0.0
        assert lab["averageHints"] == 1.0

    async def test_the_overview_field_names_are_what_the_client_expects(
        self, authed_client: AsyncClient
    ) -> None:
        """Pins the wire contract, which no type-checker can see.

        The TypeScript interface is hand-written against these exact names. A
        field named `active_users_7d` serialises as `activeUsers7D` — the alias
        generator capitalises every underscore-separated segment, including
        `7d` — which crashed the admin page with an undefined read. Named
        fields are asserted here so a rename cannot silently break the client.
        """
        response = await authed_client.get("/api/v1/admin/analytics")

        overview = response.json()["overview"]
        assert set(overview) == {
            "totalUsers",
            "activeUsersWeek",
            "newUsersWeek",
            "totalEnrollments",
            "lessonsCompleted",
            "labsCompleted",
            "quizzesTaken",
            "certificatesIssued",
        }

    async def test_the_roster_lists_learners(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/admin/roster")

        assert response.status_code == 200
        assert response.json()[0]["displayName"] == "Test Learner"

    async def test_a_student_cannot_read_analytics(
        self, authed_client: AsyncClient, client: AsyncClient
    ) -> None:
        """Gated by role, not by the UI declining to link to it."""
        token = await register(client, "student@example.com")

        response = await client.get(
            "/api/v1/admin/analytics", headers={"Authorization": f"Bearer {token}"}
        )

        assert response.status_code == 403

    async def test_an_admin_can_author_a_lab(self, authed_client: AsyncClient) -> None:
        payload = {
            "slug": "authored-lab",
            "title": "Authored lab",
            "description": "Made through the API.",
            "kind": "guided",
            "difficulty": "beginner",
            "requirements": ["Do the thing."],
            "objectives": [{"id": "obj", "title": "Do the thing", "points": 10}],
            "initialTopology": {
                "devices": [
                    {
                        "id": "pc1",
                        "kind": "pc",
                        "name": "PC1",
                        "position": {"x": 0, "y": 0},
                        "config": {},
                    }
                ],
                "links": [],
                "groups": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
            "gradingRules": [
                {
                    "id": "rule",
                    "type": "device_count",
                    "objectiveId": "obj",
                    "kind": "pc",
                    "minimum": 1,
                    "points": 10,
                }
            ],
            "isPublished": True,
        }

        created = await authed_client.post("/api/v1/admin/labs", json=payload)

        assert created.status_code == 201
        assert (await authed_client.get("/api/v1/labs/authored-lab")).status_code == 200

    async def test_authoring_rejects_an_unknown_rule_type(self, authed_client: AsyncClient) -> None:
        """The validated union is what stops a broken lab reaching a student."""
        response = await authed_client.post(
            "/api/v1/admin/labs",
            json={
                "slug": "broken-lab",
                "title": "Broken",
                "initialTopology": {
                    "devices": [],
                    "links": [],
                    "groups": [],
                    "viewport": {"x": 0, "y": 0, "zoom": 1},
                },
                "gradingRules": [{"id": "r", "type": "telepathy", "points": 10}],
            },
        )

        assert response.status_code == 422

    async def test_a_duplicate_slug_is_rejected(self, authed_client: AsyncClient) -> None:
        payload = {
            "slug": "your-first-lan",
            "title": "Clash",
            "initialTopology": {
                "devices": [],
                "links": [],
                "groups": [],
                "viewport": {"x": 0, "y": 0, "zoom": 1},
            },
        }

        response = await authed_client.post("/api/v1/admin/labs", json=payload)

        assert response.status_code == 409
