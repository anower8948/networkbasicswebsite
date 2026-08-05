"""Queries over labs and lab attempts."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import Select, func, select

from app.models.enums import AttemptStatus, Difficulty, LabKind
from app.models.lab import Lab, LabAttempt
from app.repositories.base import BaseRepository


class LabRepository(BaseRepository[Lab]):
    model = Lab

    async def get_by_slug(self, slug: str) -> Lab | None:
        result = await self.session.execute(select(Lab).where(Lab.slug == slug))
        return result.scalar_one_or_none()

    async def list_published(
        self,
        *,
        kind: LabKind | None = None,
        difficulty: Difficulty | None = None,
        lesson_id: uuid.UUID | None = None,
        include_unpublished: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[Sequence[Lab], int]:
        """Filtered page of labs, plus the total for pagination.

        `include_unpublished` exists for the instructor view; every learner path
        leaves it false so a draft lab cannot be opened by guessing its slug.
        """
        stmt: Select[tuple[Lab]] = select(Lab)
        if not include_unpublished:
            stmt = stmt.where(Lab.is_published.is_(True))
        if kind is not None:
            stmt = stmt.where(Lab.kind == kind)
        if difficulty is not None:
            stmt = stmt.where(Lab.difficulty == difficulty)
        if lesson_id is not None:
            stmt = stmt.where(Lab.lesson_id == lesson_id)

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total = int((await self.session.execute(total_stmt)).scalar_one())

        page = stmt.order_by(Lab.difficulty, Lab.title).limit(limit).offset(offset)
        result = await self.session.execute(page)
        return result.scalars().all(), total


class LabAttemptRepository(BaseRepository[LabAttempt]):
    model = LabAttempt

    async def get_open_attempt(self, user_id: uuid.UUID, lab_id: uuid.UUID) -> LabAttempt | None:
        """The in-progress attempt, so reopening a lab resumes the saved work."""
        result = await self.session.execute(
            select(LabAttempt)
            .where(
                LabAttempt.user_id == user_id,
                LabAttempt.lab_id == lab_id,
                LabAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .order_by(LabAttempt.attempt_number.desc())
        )
        return result.scalars().first()

    async def count_for_user_lab(self, user_id: uuid.UUID, lab_id: uuid.UUID) -> int:
        result = await self.session.execute(
            select(func.count(LabAttempt.id)).where(
                LabAttempt.user_id == user_id, LabAttempt.lab_id == lab_id
            )
        )
        return int(result.scalar_one())

    async def list_for_user_lab(
        self, user_id: uuid.UUID, lab_id: uuid.UUID
    ) -> Sequence[LabAttempt]:
        result = await self.session.execute(
            select(LabAttempt)
            .where(LabAttempt.user_id == user_id, LabAttempt.lab_id == lab_id)
            .order_by(LabAttempt.attempt_number.desc())
        )
        return result.scalars().all()

    async def has_passed(self, user_id: uuid.UUID, lab_id: uuid.UUID) -> bool:
        result = await self.session.execute(
            select(LabAttempt.id)
            .where(
                LabAttempt.user_id == user_id,
                LabAttempt.lab_id == lab_id,
                LabAttempt.status == AttemptStatus.PASSED,
            )
            .limit(1)
        )
        return result.first() is not None

    async def best_scores(self, user_id: uuid.UUID) -> dict[uuid.UUID, float]:
        """Best score per lab — one query to annotate the whole library."""
        result = await self.session.execute(
            select(LabAttempt.lab_id, func.max(LabAttempt.score_percent))
            .where(LabAttempt.user_id == user_id)
            .group_by(LabAttempt.lab_id)
        )
        return {row[0]: float(row[1]) for row in result.all() if row[1] is not None}

    async def best_status(self, user_id: uuid.UUID) -> dict[uuid.UUID, AttemptStatus]:
        """The most meaningful status per lab: passed beats anything else."""
        result = await self.session.execute(
            select(LabAttempt.lab_id, LabAttempt.status).where(LabAttempt.user_id == user_id)
        )
        best: dict[uuid.UUID, AttemptStatus] = {}
        for lab_id, status in result.all():
            if best.get(lab_id) is AttemptStatus.PASSED:
                continue
            best[lab_id] = status
        return best

    async def count_passed(self, user_id: uuid.UUID) -> int:
        """Distinct labs passed — the metric several achievements read."""
        result = await self.session.execute(
            select(func.count(func.distinct(LabAttempt.lab_id))).where(
                LabAttempt.user_id == user_id,
                LabAttempt.status == AttemptStatus.PASSED,
            )
        )
        return int(result.scalar_one())
