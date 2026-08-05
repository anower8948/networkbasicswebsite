"""Tests for quiz delivery and grading."""

from __future__ import annotations

import json
from typing import Any

from httpx import AsyncClient

COURSE = "/api/v1/courses/network-fundamentals"
LESSON = "/api/v1/lessons/network-fundamentals/osi-model"
ENROLL = f"{COURSE}/enroll"
PROGRESS = "/api/v1/users/me/progress"


def result_for(result: dict[str, Any], quiz: dict[str, Any], question_type: str) -> dict[str, Any]:
    """Find the result for the first question of a given type.

    Questions are delivered shuffled but results are returned in stored order,
    so they must be paired by `questionId` — never by position.
    """
    question = next(q for q in quiz["questions"] if q["questionType"] == question_type)
    return next(r for r in result["results"] if r["questionId"] == question["id"])


async def start_attempt(client: AsyncClient) -> dict[str, Any]:
    """Enrol and open an attempt on the OSI lesson's quiz."""
    await client.post(ENROLL)
    quiz_id = (await client.get(LESSON)).json()["quizId"]
    response = await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")
    assert response.status_code == 200, response.text
    return response.json()


def answer_correctly(quiz: dict[str, Any]) -> list[dict[str, Any]]:
    """Build a fully correct submission from the seeded content.

    Correct answers are *not* in the payload by design, so this mirrors what a
    learner who knows the material would send.
    """
    known_text = {
        "What is the Layer 3 protocol data unit called?": "packet",
    }
    correct_options = {
        "Which OSI layer is responsible for logical addressing and path selection?": [
            "Layer 3 — Network"
        ],
        "A switch forwards traffic based on MAC addresses. At which layer does it operate?": [
            "Layer 2"
        ],
        "Select every statement that is true of UDP.": [
            "It is connectionless",
            "Its header is 8 bytes",
        ],
        "TCP is connection-oriented and guarantees delivery.": ["True"],
    }

    answers: list[dict[str, Any]] = []
    for question in quiz["questions"]:
        prompt = question["prompt"]
        answer: dict[str, Any] = {"questionId": question["id"]}

        if prompt in known_text:
            answer["text"] = known_text[prompt]
        elif prompt in correct_options:
            wanted = correct_options[prompt]
            answer["optionIds"] = [
                option["id"] for option in question["options"] if option["text"] in wanted
            ]
        elif question["questionType"] == "ordering":
            answer["values"] = ["SYN", "SYN-ACK", "ACK"]
        answers.append(answer)

    return answers


class TestAttemptDelivery:
    async def test_starting_an_attempt_returns_questions(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)

        assert quiz["title"]
        assert len(quiz["questions"]) == 6
        assert quiz["attemptNumber"] == 1

    async def test_the_payload_never_reveals_the_answers(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """The core guarantee: a learner cannot read the key off the wire."""
        quiz = await start_attempt(authed_client)
        raw = json.dumps(quiz)

        assert "isCorrect" not in raw
        assert "is_correct" not in raw
        assert "answerKey" not in raw
        assert "explanation" not in raw

        for question in quiz["questions"]:
            for option in question["options"]:
                assert set(option) == {"id", "text", "orderIndex"}

    async def test_refreshing_resumes_the_same_attempt(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """A page refresh must not burn one of a limited number of attempts."""
        first = await start_attempt(authed_client)
        quiz_id = first["id"]
        second = (await authed_client.post(f"/api/v1/quizzes/{quiz_id}/attempts")).json()

        assert second["attemptId"] == first["attemptId"]
        assert second["attemptNumber"] == 1

    async def test_question_order_is_stable_within_an_attempt(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """Shuffling is seeded on the attempt, so a refresh does not reorder."""
        first = await start_attempt(authed_client)
        second = (await authed_client.post(f"/api/v1/quizzes/{first['id']}/attempts")).json()

        assert [q["id"] for q in first["questions"]] == [q["id"] for q in second["questions"]]

    async def test_attempts_require_authentication(
        self, client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz_id = (await client.get(LESSON)).json()["quizId"]
        assert (await client.post(f"/api/v1/quizzes/{quiz_id}/attempts")).status_code == 401


class TestGrading:
    async def test_a_perfect_submission_passes_and_pays_xp(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)

        response = await authed_client.post(
            f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
            json={"answers": answer_correctly(quiz)},
        )

        assert response.status_code == 200
        result = response.json()
        assert result["passed"] is True
        assert result["scorePercent"] == 100.0
        assert result["xpAwarded"] == 25
        assert result["status"] == "passed"

    async def test_an_empty_submission_fails(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)
        blank = [{"questionId": question["id"]} for question in quiz["questions"]]

        result = (
            await authed_client.post(
                f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
                json={"answers": blank},
            )
        ).json()

        assert result["passed"] is False
        assert result["scorePercent"] == 0.0
        assert result["xpAwarded"] == 0

    async def test_results_explain_each_question(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """Feedback arrives only after submission."""
        quiz = await start_attempt(authed_client)
        result = (
            await authed_client.post(
                f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
                json={"answers": answer_correctly(quiz)},
            )
        ).json()

        assert len(result["results"]) == 6
        for entry in result["results"]:
            assert entry["explanation"], "every seeded question should explain itself"
            assert "isCorrect" in entry

    async def test_partial_selection_on_multi_choice_is_wrong(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        """Half-right is wrong: selecting one of two correct options fails."""
        quiz = await start_attempt(authed_client)

        answers = []
        for question in quiz["questions"]:
            entry: dict[str, Any] = {"questionId": question["id"]}
            if question["questionType"] == "multiple_choice":
                entry["optionIds"] = [
                    option["id"]
                    for option in question["options"]
                    if option["text"] == "It is connectionless"
                ]
            answers.append(entry)

        result = (
            await authed_client.post(
                f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
                json={"answers": answers},
            )
        ).json()

        multi = result_for(result, quiz, "multiple_choice")
        assert multi["isCorrect"] is False

    async def test_fill_blank_ignores_case_and_spacing(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)

        answers = [
            {"questionId": question["id"], "text": "  A PACKET  "}
            if question["questionType"] == "fill_blank"
            else {"questionId": question["id"]}
            for question in quiz["questions"]
        ]
        result = (
            await authed_client.post(
                f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
                json={"answers": answers},
            )
        ).json()

        blank = result_for(result, quiz, "fill_blank")
        assert blank["isCorrect"] is True

    async def test_ordering_must_match_exactly(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)

        answers = [
            {"questionId": question["id"], "values": ["ACK", "SYN", "SYN-ACK"]}
            if question["questionType"] == "ordering"
            else {"questionId": question["id"]}
            for question in quiz["questions"]
        ]
        result = (
            await authed_client.post(
                f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
                json={"answers": answers},
            )
        ).json()

        ordering = result_for(result, quiz, "ordering")
        assert ordering["isCorrect"] is False

    async def test_an_attempt_cannot_be_submitted_twice(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)
        payload = {"answers": answer_correctly(quiz)}
        url = f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit"

        assert (await authed_client.post(url, json=payload)).status_code == 200
        replay = await authed_client.post(url, json=payload)

        assert replay.status_code == 409
        assert replay.json()["error"]["code"] == "attempt_already_submitted"

    async def test_cannot_submit_another_learners_attempt(
        self, client: AsyncClient, seeded_catalog: dict[str, int], user_payload: dict[str, str]
    ) -> None:
        """Ownership is checked before existence is disclosed."""
        victim = await client.post("/api/v1/auth/register", json=user_payload)
        client.headers["Authorization"] = f"Bearer {victim.json()['accessToken']}"
        quiz = await start_attempt(client)

        attacker = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "attacker@example.com",
                "username": "attacker",
                "password": "AttackerPass24",
            },
        )
        client.headers["Authorization"] = f"Bearer {attacker.json()['accessToken']}"

        response = await client.post(
            f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
            json={"answers": [{"questionId": quiz["questions"][0]["id"]}]},
        )
        assert response.status_code == 404


class TestQuizXP:
    async def test_passing_twice_pays_once(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)
        await authed_client.post(
            f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
            json={"answers": answer_correctly(quiz)},
        )
        after_first = (await authed_client.get(PROGRESS)).json()["totalXp"]

        second = await start_attempt(authed_client)
        result = (
            await authed_client.post(
                f"/api/v1/quizzes/attempts/{second['attemptId']}/submit",
                json={"answers": answer_correctly(second)},
            )
        ).json()

        assert result["xpAwarded"] == 0
        assert (await authed_client.get(PROGRESS)).json()["totalXp"] == after_first

    async def test_passing_increments_the_quiz_counter_once(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)
        await authed_client.post(
            f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
            json={"answers": answer_correctly(quiz)},
        )
        second = await start_attempt(authed_client)
        await authed_client.post(
            f"/api/v1/quizzes/attempts/{second['attemptId']}/submit",
            json={"answers": answer_correctly(second)},
        )

        assert (await authed_client.get(PROGRESS)).json()["quizzesPassed"] == 1

    async def test_attempt_history_is_listed(
        self, authed_client: AsyncClient, seeded_catalog: dict[str, int]
    ) -> None:
        quiz = await start_attempt(authed_client)
        await authed_client.post(
            f"/api/v1/quizzes/attempts/{quiz['attemptId']}/submit",
            json={"answers": answer_correctly(quiz)},
        )

        history = (await authed_client.get(f"/api/v1/quizzes/{quiz['id']}/attempts")).json()

        assert len(history) == 1
        assert history[0]["scorePercent"] == 100.0
        assert history[0]["status"] == "passed"
