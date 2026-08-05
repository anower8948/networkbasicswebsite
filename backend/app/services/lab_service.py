"""Lab delivery, autosave, and grading.

The learner-facing half of Part 8. Three things it is careful about:

**Grading rules and injected faults never reach the browser.** `LabDetail` is
built field by field rather than dumped from the model, so a rule added later
cannot leak by accident — the same discipline the quiz payload uses for answer
keys.

**Checking your work is free; submitting is final.** A student should be able to
press "check" after every change and read what is still wrong: that iteration is
the lab. Only `submit` closes the attempt, awards XP, and reveals what the
troubleshooting faults were.

**XP is paid once per lab, ever.** Re-passing pays nothing, which is enforced by
the ledger's reference deduplication rather than by a flag here.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.models.enums import AttemptStatus, Difficulty, LabKind, XPReason
from app.models.lab import Lab, LabAttempt
from app.models.user import User
from app.repositories.lab import LabAttemptRepository, LabRepository
from app.schemas.lab import (
    CheckResult,
    FaultInjection,
    GradingRule,
    HintResponse,
    LabAttemptRead,
    LabDetail,
    LabGradeResult,
    LabObjective,
    LabSummary,
    WorkingTopologyUpdate,
)
from app.schemas.topology import TopologyDocument
from app.services.achievement_service import award_new_achievements
from app.services.fault_injection import apply_faults
from app.services.grading import LabGrader
from app.services.progress_service import ProgressService

logger = get_logger(__name__)

# Parsing the authoring JSON back into models happens on every grade, so the
# adapters are built once at import rather than per call.
_RULES = TypeAdapter(list[GradingRule])
_FAULTS = TypeAdapter(list[FaultInjection])
_OBJECTIVES = TypeAdapter(list[LabObjective])
_RESULTS = TypeAdapter(list[CheckResult])


class LabNotFound(NotFoundError):
    code = "lab_not_found"
    message = "Lab not found."


class AttemptAlreadySubmitted(ConflictError):
    code = "attempt_already_submitted"
    message = "This attempt has already been submitted."


class LabService:
    """Serves labs to learners and grades what they build."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.labs = LabRepository(session)
        self.attempts = LabAttemptRepository(session)
        self.progress = ProgressService(session)

    # ------------------------------------------------------------------ #
    # Library
    # ------------------------------------------------------------------ #
    async def list_labs(
        self,
        user: User | None,
        *,
        kind: LabKind | None = None,
        difficulty: Difficulty | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[LabSummary], int]:
        labs, total = await self.labs.list_published(
            kind=kind, difficulty=difficulty, limit=limit, offset=offset
        )

        # Two queries for the whole page rather than two per lab.
        scores: dict[uuid.UUID, float] = {}
        statuses: dict[uuid.UUID, AttemptStatus] = {}
        if user is not None:
            scores = await self.attempts.best_scores(user.id)
            statuses = await self.attempts.best_status(user.id)

        return [self._summary(lab, scores.get(lab.id), statuses.get(lab.id)) for lab in labs], total

    @staticmethod
    def _summary(lab: Lab, best_score: float | None, status: AttemptStatus | None) -> LabSummary:
        return LabSummary(
            id=lab.id,
            slug=lab.slug,
            title=lab.title,
            description=lab.description,
            kind=lab.kind,
            scenario_type=lab.scenario_type,
            difficulty=lab.difficulty,
            estimated_minutes=lab.estimated_minutes,
            passing_score=lab.passing_score,
            xp_reward=lab.xp_reward,
            objective_count=len(lab.objectives),
            best_score=best_score,
            status=status,
        )

    async def get_lab(self, user: User | None, slug: str) -> LabDetail:
        """The learner-safe projection: requirements and objectives, no answers."""
        lab = await self.labs.get_by_slug(slug)
        if lab is None or not lab.is_published:
            raise LabNotFound()

        best_score = None
        status = None
        if user is not None:
            best_score = (await self.attempts.best_scores(user.id)).get(lab.id)
            status = (await self.attempts.best_status(user.id)).get(lab.id)

        summary = self._summary(lab, best_score, status)
        return LabDetail(
            **summary.model_dump(),
            requirements=list(lab.requirements),
            objectives=_OBJECTIVES.validate_python(lab.objectives),
            time_limit_seconds=lab.time_limit_seconds,
        )

    # ------------------------------------------------------------------ #
    # Attempts
    # ------------------------------------------------------------------ #
    async def start_attempt(self, user: User, slug: str) -> LabAttemptRead:
        """Open a new attempt, or resume the one already in progress.

        Resuming matters more here than for a quiz: a lab holds half an hour of
        the learner's work in `working_topology`, and starting fresh on a page
        refresh would throw it away.
        """
        lab = await self.labs.get_by_slug(slug)
        if lab is None or not lab.is_published:
            raise LabNotFound()

        attempt = await self.attempts.get_open_attempt(user.id, lab.id)
        if attempt is None:
            used = await self.attempts.count_for_user_lab(user.id, lab.id)
            attempt = LabAttempt(
                user_id=user.id,
                lab_id=lab.id,
                attempt_number=used + 1,
                status=AttemptStatus.IN_PROGRESS,
                started_at=utcnow(),
                working_topology=self._starting_topology(lab),
            )
            self.attempts.add(attempt)
            await self.progress.record_activity(user, commit=False)
            await self.session.commit()

        return self._attempt_read(attempt)

    @staticmethod
    def _starting_topology(lab: Lab) -> dict[str, Any]:
        """The document the student begins from.

        For a troubleshooting lab this is the authored *working* network with
        faults applied — done here, on the server, so the intact original is
        never sent to the browser.
        """
        document = TopologyDocument.model_validate(lab.initial_topology or {})
        if lab.fault_injections:
            document = apply_faults(document, _FAULTS.validate_python(lab.fault_injections))
        return document.model_dump(mode="json", by_alias=True)

    async def save_working_topology(
        self, user: User, attempt_id: uuid.UUID, payload: WorkingTopologyUpdate
    ) -> LabAttemptRead:
        """Autosave from the canvas."""
        attempt = await self._own_attempt(user, attempt_id)
        if attempt.status is not AttemptStatus.IN_PROGRESS:
            raise AttemptAlreadySubmitted()

        attempt.working_topology = payload.document.model_dump(mode="json", by_alias=True)
        if payload.time_spent_seconds:
            attempt.time_spent_seconds = payload.time_spent_seconds
        await self.session.commit()
        return self._attempt_read(attempt)

    async def hint(self, user: User, attempt_id: uuid.UUID, objective_id: str) -> HintResponse:
        """Reveal an objective's hint, counting it against the attempt.

        Hints are not rationed — a stuck learner who cannot get unstuck simply
        stops. The count is recorded so an instructor can see where a lab is
        harder than it was meant to be.
        """
        attempt = await self._own_attempt(user, attempt_id)
        lab = await self.labs.get(attempt.lab_id)
        if lab is None:
            raise LabNotFound()

        objectives = _OBJECTIVES.validate_python(lab.objectives)
        objective = next((item for item in objectives if item.id == objective_id), None)
        if objective is None:
            raise NotFoundError("That objective is not part of this lab.")

        if objective.hint:
            attempt.hints_used += 1
            await self.session.commit()

        return HintResponse(
            objective_id=objective_id,
            hint=objective.hint,
            hints_used=attempt.hints_used,
        )

    # ------------------------------------------------------------------ #
    # Grading
    # ------------------------------------------------------------------ #
    async def check(self, user: User, attempt_id: uuid.UUID) -> LabGradeResult:
        """Grade the current work without closing the attempt."""
        return await self._grade(user, attempt_id, final=False)

    async def submit(self, user: User, attempt_id: uuid.UUID) -> LabGradeResult:
        """Grade, close the attempt, and award XP on a first pass."""
        return await self._grade(user, attempt_id, final=True)

    async def _grade(self, user: User, attempt_id: uuid.UUID, *, final: bool) -> LabGradeResult:
        attempt = await self._own_attempt(user, attempt_id)
        if attempt.status is not AttemptStatus.IN_PROGRESS:
            raise AttemptAlreadySubmitted()

        lab = await self.labs.get(attempt.lab_id)
        if lab is None:
            raise LabNotFound()

        document = TopologyDocument.model_validate(attempt.working_topology or {})
        report = LabGrader(document).grade(
            _RULES.validate_python(lab.grading_rules),
            _OBJECTIVES.validate_python(lab.objectives),
        )

        score = report.score_percent
        passed = score >= lab.passing_score

        attempt.check_results = [item.model_dump(mode="json") for item in report.results]
        attempt.score_percent = score

        xp_awarded = 0
        stats = await self.progress.stats_for(user)
        total_xp, level, leveled_up = stats.total_xp, stats.level, False

        if final:
            attempt.status = AttemptStatus.PASSED if passed else AttemptStatus.FAILED
            attempt.submitted_at = utcnow()

            if passed:
                grant = await self.progress.grant_xp(
                    user,
                    lab.xp_reward,
                    XPReason.LAB_COMPLETED,
                    reference_type="lab",
                    reference_id=lab.id,
                    commit=False,
                )
                xp_awarded, total_xp, level, leveled_up = (
                    grant.awarded,
                    grant.total_xp,
                    grant.level,
                    grant.leveled_up,
                )
                if not grant.was_duplicate:
                    stats.labs_completed += 1

        await self.progress.record_activity(user, commit=False)
        await self.session.commit()

        # Only a real submission can earn a badge — checking your work as often
        # as you like should not be a way to farm them.
        new_achievements = (
            await award_new_achievements(self.session, user) if final and passed else []
        )
        if new_achievements:
            # Badge XP is granted after the totals above were read.
            stats = await self.progress.stats_for(user)
            leveled_up = leveled_up or stats.level > level
            total_xp, level = stats.total_xp, stats.level

        if final:
            logger.info(
                "Lab submitted",
                extra={
                    "user_id": str(user.id),
                    "lab_id": str(lab.id),
                    "score": score,
                    "passed": passed,
                },
            )

        return LabGradeResult(
            attempt_id=attempt.id,
            lab_id=lab.id,
            status=attempt.status,
            passed=passed,
            score_percent=score,
            points_earned=report.points_earned,
            points_possible=report.points_possible,
            passing_score=lab.passing_score,
            results=report.results,
            objectives=report.objectives,
            xp_awarded=xp_awarded,
            total_xp=total_xp,
            level=level,
            leveled_up=leveled_up,
            # The post-mortem: only once they have actually fixed it.
            fault_explanations=self._fault_explanations(lab) if (final and passed) else [],
            new_achievements=new_achievements,
        )

    @staticmethod
    def _fault_explanations(lab: Lab) -> list[str]:
        if not lab.fault_injections:
            return []
        faults = _FAULTS.validate_python(lab.fault_injections)
        return [fault.explanation for fault in faults if fault.explanation]

    # ------------------------------------------------------------------ #
    # Shared
    # ------------------------------------------------------------------ #
    async def _own_attempt(self, user: User, attempt_id: uuid.UUID) -> LabAttempt:
        attempt = await self.attempts.get(attempt_id)
        # Ownership before existence, so this cannot probe other learners' work.
        if attempt is None or attempt.user_id != user.id:
            raise NotFoundError("Attempt not found.")
        return attempt

    @staticmethod
    def _attempt_read(attempt: LabAttempt) -> LabAttemptRead:
        return LabAttemptRead(
            id=attempt.id,
            lab_id=attempt.lab_id,
            attempt_number=attempt.attempt_number,
            status=attempt.status,
            working_topology=attempt.working_topology,
            check_results=_RESULTS.validate_python(attempt.check_results),
            score_percent=attempt.score_percent,
            hints_used=attempt.hints_used,
            time_spent_seconds=attempt.time_spent_seconds,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
        )
