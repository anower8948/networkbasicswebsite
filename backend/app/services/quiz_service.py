"""Quiz delivery and grading.

Grading is **entirely server-side** and correct answers never leave the server
before submission. The pre-submission payload
(:class:`~app.schemas.learning.QuizForAttempt`) is a separate type from the
post-submission one, so an answer key cannot be leaked by accident.

Question types and how each is graded:

===================  ==========================================================
single_choice        exactly the one correct option
true_false           same as single choice, with two options
multiple_choice      the selected set must equal the correct set — partial
                     credit is not given, because "TCP and UDP are both
                     connection-oriented" is wrong even though half is right
fill_blank           text match against `answer_key.accepted`, normalised
subnet_calc          text match with IP-aware normalisation
cli_command          text match with Cisco command normalisation
ordering             the submitted sequence must equal `answer_key.order`
matching             every pair must match `answer_key.pairs`
===================  ==========================================================
"""

from __future__ import annotations

import random
import re
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.catalog import Quiz, QuizQuestion
from app.models.enums import AttemptStatus, ProgressStatus, QuestionType, XPReason
from app.models.progress import QuizAttempt
from app.models.user import User
from app.repositories.learning import (
    LessonProgressRepository,
    QuizAttemptRepository,
    QuizRepository,
)
from app.schemas.learning import (
    AnswerKeyPayload,
    QuestionResult,
    QuizAnswer,
    QuizForAttempt,
    QuizOptionForAttempt,
    QuizQuestionForAttempt,
    QuizResult,
    QuizSubmission,
)
from app.services.achievement_service import award_new_achievements
from app.services.progress_service import ProgressService

logger = get_logger(__name__)

# XP for passing a quiz, paid once per quiz.
QUIZ_PASS_XP = 25


class QuizNotFound(NotFoundError):
    code = "quiz_not_found"
    message = "Quiz not found."


class AttemptLimitReached(ConflictError):
    code = "attempt_limit_reached"
    message = "You have used every attempt for this quiz."


class AttemptAlreadySubmitted(ConflictError):
    code = "attempt_already_submitted"
    message = "This attempt has already been submitted."


# --------------------------------------------------------------------------- #
# Answer normalisation
# --------------------------------------------------------------------------- #
def _normalise_text(value: str) -> str:
    """Collapse whitespace and case for free-text comparison."""
    return re.sub(r"\s+", " ", value).strip().lower()


def _normalise_cli(value: str) -> str:
    """Normalise a Cisco command for comparison.

    Real IOS accepts abbreviations and is whitespace-tolerant, so exact string
    equality would fail a learner who typed a perfectly valid command. This
    collapses whitespace, drops case, and strips a trailing carriage return —
    the abbreviation table lives in the answer key's `accepted` list, which is
    where an author can be explicit about which forms they will take.
    """
    return _normalise_text(value.replace("\r", ""))


def _normalise_ip_answer(value: str) -> str:
    """Normalise a subnetting answer.

    Accepts `192.168.1.0/24`, `192.168.1.0 /24` and `192.168.1.0255.255.255.0`
    style spacing differences by removing spaces around the slash and
    collapsing the rest.
    """
    collapsed = _normalise_text(value)
    return re.sub(r"\s*/\s*", "/", collapsed)


class QuizService:
    """Delivers quizzes and grades submissions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.quizzes = QuizRepository(session)
        self.attempts = QuizAttemptRepository(session)
        self.lesson_progress = LessonProgressRepository(session)
        self.progress = ProgressService(session)

    # ------------------------------------------------------------------ #
    # Delivery
    # ------------------------------------------------------------------ #
    async def start_attempt(self, user: User, quiz_id: uuid.UUID) -> QuizForAttempt:
        """Open (or resume) an attempt and return the learner-safe payload."""
        quiz = await self.quizzes.get_with_questions(quiz_id)
        if quiz is None:
            raise QuizNotFound()

        attempt = await self.attempts.get_open_attempt(user.id, quiz.id)
        if attempt is None:
            used = await self.attempts.count_for_user_quiz(user.id, quiz.id)
            if quiz.max_attempts is not None and used >= quiz.max_attempts:
                raise AttemptLimitReached()

            attempt = QuizAttempt(
                user_id=user.id,
                quiz_id=quiz.id,
                attempt_number=used + 1,
                status=AttemptStatus.IN_PROGRESS,
                started_at=utcnow(),
                points_possible=sum(question.points for question in quiz.questions),
            )
            self.attempts.add(attempt)
            await self.session.commit()

        questions = list(quiz.questions)
        if quiz.shuffle_questions:
            # Seeded on the attempt id so a refresh shows the same order — a
            # reshuffle mid-attempt would be disorienting.
            random.Random(str(attempt.id)).shuffle(questions)

        remaining = (
            None
            if quiz.max_attempts is None
            else max(quiz.max_attempts - attempt.attempt_number, 0)
        )

        return QuizForAttempt(
            id=quiz.id,
            lesson_id=quiz.lesson_id,
            title=quiz.title,
            instructions=quiz.instructions,
            passing_score=quiz.passing_score,
            time_limit_seconds=quiz.time_limit_seconds,
            questions=[self._question_for_attempt(question, attempt.id) for question in questions],
            attempt_id=attempt.id,
            attempt_number=attempt.attempt_number,
            attempts_remaining=remaining,
        )

    @staticmethod
    def _question_for_attempt(
        question: QuizQuestion, attempt_id: uuid.UUID
    ) -> QuizQuestionForAttempt:
        """Project a question without any correctness information."""
        options = [
            QuizOptionForAttempt(id=option.id, text=option.text, order_index=option.order_index)
            for option in sorted(question.options, key=lambda item: item.order_index)
        ]
        # Ordering questions ship shuffled, or the correct sequence would
        # already be on screen.
        if question.question_type is QuestionType.ORDERING:
            random.Random(f"{attempt_id}:{question.id}").shuffle(options)

        match_targets: list[str] = []
        if question.question_type is QuestionType.MATCHING and question.answer_key:
            key = AnswerKeyPayload.model_validate(question.answer_key)
            match_targets = sorted(set(key.pairs.values()))
            random.Random(f"{attempt_id}:{question.id}:t").shuffle(match_targets)

        return QuizQuestionForAttempt(
            id=question.id,
            prompt=question.prompt,
            question_type=question.question_type,
            media_url=question.media_url,
            points=question.points,
            order_index=question.order_index,
            options=options,
            match_targets=match_targets,
        )

    # ------------------------------------------------------------------ #
    # Grading
    # ------------------------------------------------------------------ #
    async def submit(
        self, user: User, attempt_id: uuid.UUID, submission: QuizSubmission
    ) -> QuizResult:
        """Grade a submission, persist it, and award XP on a first pass."""
        attempt = await self.attempts.get(attempt_id)
        if attempt is None or attempt.user_id != user.id:
            # Ownership before existence, so this cannot probe other attempts.
            raise NotFoundError("Attempt not found.")
        if attempt.status is not AttemptStatus.IN_PROGRESS:
            raise AttemptAlreadySubmitted()

        quiz = await self.quizzes.get_with_questions(attempt.quiz_id)
        if quiz is None:
            raise QuizNotFound()

        answers = {answer.question_id: answer for answer in submission.answers}
        results: list[QuestionResult] = []
        points_earned = 0
        points_possible = 0

        for question in quiz.questions:
            points_possible += question.points
            result = self._grade_question(question, answers.get(question.id))
            points_earned += result.points_earned
            results.append(result)

        score = round((points_earned / points_possible) * 100, 1) if points_possible else 0.0
        passed = score >= quiz.passing_score

        # Record the raw responses so the attempt can be reviewed, and re-graded
        # if an answer key is later corrected.
        attempt.responses = {
            str(answer.question_id): answer.model_dump(mode="json") for answer in submission.answers
        }
        attempt.points_earned = points_earned
        attempt.points_possible = points_possible
        attempt.score_percent = score
        attempt.status = AttemptStatus.PASSED if passed else AttemptStatus.FAILED
        attempt.submitted_at = utcnow()

        xp_awarded = 0
        total_xp = 0
        level = 1
        leveled_up = False

        if passed:
            grant = await self.progress.grant_xp(
                user,
                QUIZ_PASS_XP,
                XPReason.QUIZ_PASSED,
                reference_type="quiz",
                reference_id=quiz.id,
                commit=False,
            )
            xp_awarded, total_xp, level, leveled_up = (
                grant.awarded,
                grant.total_xp,
                grant.level,
                grant.leveled_up,
            )
            if not grant.was_duplicate:
                stats = await self.progress.stats_for(user)
                stats.quizzes_passed += 1

            # Passing the quiz completes its lesson, so a quiz-type lesson does
            # not need a separate "mark complete" click.
            await self._mark_lesson_started(user, quiz)
        else:
            stats = await self.progress.stats_for(user)
            total_xp, level = stats.total_xp, stats.level

        await self.progress.record_activity(user, commit=False)
        await self.session.commit()

        # After the commit: badges grant XP of their own, so evaluating them
        # from inside the grant path would recurse.
        new_achievements = await award_new_achievements(self.session, user)
        if new_achievements:
            # Those grants landed after the totals above were read.
            stats = await self.progress.stats_for(user)
            leveled_up = leveled_up or stats.level > level
            total_xp, level = stats.total_xp, stats.level

        used = await self.attempts.count_for_user_quiz(user.id, quiz.id)
        remaining = None if quiz.max_attempts is None else max(quiz.max_attempts - used, 0)

        logger.info(
            "Quiz submitted",
            extra={
                "user_id": str(user.id),
                "quiz_id": str(quiz.id),
                "score": score,
                "passed": passed,
            },
        )

        return QuizResult(
            attempt_id=attempt.id,
            quiz_id=quiz.id,
            lesson_id=quiz.lesson_id,
            status=attempt.status,
            passed=passed,
            score_percent=score,
            points_earned=points_earned,
            points_possible=points_possible,
            passing_score=quiz.passing_score,
            attempt_number=attempt.attempt_number,
            attempts_remaining=remaining,
            results=results,
            xp_awarded=xp_awarded,
            total_xp=total_xp,
            level=level,
            leveled_up=leveled_up,
            new_achievements=new_achievements,
        )

    async def _mark_lesson_started(self, user: User, quiz: Quiz) -> None:
        """Ensure a progress row exists for the quiz's lesson."""
        record = await self.lesson_progress.get_for_user_lesson(user.id, quiz.lesson_id)
        if record is None:
            from app.models.progress import LessonProgress

            record = LessonProgress(
                user_id=user.id,
                lesson_id=quiz.lesson_id,
                status=ProgressStatus.IN_PROGRESS,
            )
            self.lesson_progress.add(record)
            await self.session.flush()

    # ------------------------------------------------------------------ #
    # Per-question grading
    # ------------------------------------------------------------------ #
    def _grade_question(self, question: QuizQuestion, answer: QuizAnswer | None) -> QuestionResult:
        """Grade one question. A missing answer scores zero, never an error."""
        correct_options = {option.id for option in question.options if option.is_correct}
        key = (
            AnswerKeyPayload.model_validate(question.answer_key)
            if question.answer_key
            else AnswerKeyPayload()
        )

        is_correct = False
        if answer is not None:
            is_correct = self._is_answer_correct(question, answer, correct_options, key)

        return QuestionResult(
            question_id=question.id,
            is_correct=is_correct,
            points_earned=question.points if is_correct else 0,
            points_possible=question.points,
            explanation=question.explanation,
            correct_option_ids=sorted(correct_options, key=str),
            correct_text=key.text,
            correct_order=key.order,
            correct_pairs=key.pairs,
        )

    def _is_answer_correct(
        self,
        question: QuizQuestion,
        answer: QuizAnswer,
        correct_options: set[uuid.UUID],
        key: AnswerKeyPayload,
    ) -> bool:
        kind = question.question_type

        if kind in (
            QuestionType.SINGLE_CHOICE,
            QuestionType.TRUE_FALSE,
            QuestionType.MULTIPLE_CHOICE,
        ):
            # Set equality for all three: selecting a correct option *and* an
            # incorrect one is not a partially right answer.
            return set(answer.option_ids) == correct_options

        if kind in (QuestionType.FILL_BLANK, QuestionType.CLI_COMMAND, QuestionType.SUBNET_CALC):
            if not answer.text:
                return False
            normalise = {
                QuestionType.FILL_BLANK: _normalise_text,
                QuestionType.CLI_COMMAND: _normalise_cli,
                QuestionType.SUBNET_CALC: _normalise_ip_answer,
            }[kind]

            accepted = [*key.accepted]
            if key.text:
                accepted.append(key.text)
            if not accepted:
                return False

            if key.case_sensitive:
                return answer.text.strip() in {item.strip() for item in accepted}
            return normalise(answer.text) in {normalise(item) for item in accepted}

        if kind is QuestionType.ORDERING:
            return [str(value) for value in answer.values] == list(key.order)

        if kind is QuestionType.MATCHING:
            if not key.pairs:
                return False
            return {str(k): str(v) for k, v in answer.pairs.items()} == key.pairs

        return False
