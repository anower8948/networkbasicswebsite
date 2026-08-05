"""Aggregate analytics for instructors and admins.

Everything is computed with GROUP BY in the database rather than by loading rows
and counting in Python. On a platform with ten learners the difference is
invisible; the point is that it stays a handful of queries at ten thousand.

Nothing here is per-learner *behaviour*. The roster shows standing — level, XP,
counts, last-active — because an instructor needs to know who is falling behind.
It does not show what anyone did, or when, or for how long.
"""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import Select, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.models.catalog import Course, Quiz
from app.models.enums import AttemptStatus, EnrollmentStatus, ProgressStatus
from app.models.gamification import Certificate
from app.models.lab import Lab, LabAttempt
from app.models.progress import Enrollment, LessonProgress, QuizAttempt
from app.models.user import User, UserStats
from app.schemas.analytics import (
    AnalyticsReport,
    CoursePerformance,
    LabPerformance,
    PlatformOverview,
    QuizQuestionStat,
    RosterEntry,
)

RECENT_DAYS = 7


def _rate(numerator: int | float, denominator: int | float) -> float:
    return round((numerator / denominator) * 100, 1) if denominator else 0.0


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def report(self) -> AnalyticsReport:
        return AnalyticsReport(
            overview=await self.overview(),
            courses=await self.course_performance(),
            labs=await self.lab_performance(),
            quizzes=await self.quiz_performance(),
        )

    # ------------------------------------------------------------------ #
    # Overview
    # ------------------------------------------------------------------ #
    async def overview(self) -> PlatformOverview:
        since = utcnow() - timedelta(days=RECENT_DAYS)

        async def scalar(statement: Select[tuple[int]]) -> int:
            result = await self.session.execute(statement)
            return int(result.scalar_one())

        return PlatformOverview(
            total_users=await scalar(select(func.count(User.id))),
            active_users_week=await scalar(
                select(func.count(UserStats.user_id)).where(UserStats.last_activity_date >= since)
            ),
            new_users_week=await scalar(
                select(func.count(User.id)).where(User.created_at >= since)
            ),
            total_enrollments=await scalar(select(func.count(Enrollment.id))),
            lessons_completed=await scalar(
                select(func.count(LessonProgress.id)).where(
                    LessonProgress.status == ProgressStatus.COMPLETED
                )
            ),
            labs_completed=await scalar(
                select(func.count(LabAttempt.id)).where(LabAttempt.status == AttemptStatus.PASSED)
            ),
            quizzes_taken=await scalar(select(func.count(QuizAttempt.id))),
            certificates_issued=await scalar(select(func.count(Certificate.id))),
        )

    # ------------------------------------------------------------------ #
    # Content performance
    # ------------------------------------------------------------------ #
    async def course_performance(self) -> list[CoursePerformance]:
        completed = func.sum(case((Enrollment.status == EnrollmentStatus.COMPLETED, 1), else_=0))
        result = await self.session.execute(
            select(
                Course.id,
                Course.slug,
                Course.title,
                func.count(Enrollment.id),
                completed,
                func.coalesce(func.avg(Enrollment.progress_percent), 0.0),
            )
            .outerjoin(Enrollment, Enrollment.course_id == Course.id)
            .group_by(Course.id)
            .order_by(Course.order_index)
        )

        report: list[CoursePerformance] = []
        for course_id, slug, title, enrollments, completions, average in result.all():
            completions = int(completions or 0)
            report.append(
                CoursePerformance(
                    course_id=course_id,
                    slug=slug,
                    title=title,
                    enrollments=int(enrollments),
                    completions=completions,
                    completion_rate=_rate(completions, int(enrollments)),
                    average_progress=round(float(average), 1),
                )
            )
        return report

    async def lab_performance(self) -> list[LabPerformance]:
        passes = func.sum(case((LabAttempt.status == AttemptStatus.PASSED, 1), else_=0))
        result = await self.session.execute(
            select(
                Lab.id,
                Lab.slug,
                Lab.title,
                func.count(LabAttempt.id),
                passes,
                func.coalesce(func.avg(LabAttempt.score_percent), 0.0),
                func.coalesce(func.avg(LabAttempt.hints_used), 0.0),
            )
            .outerjoin(LabAttempt, LabAttempt.lab_id == Lab.id)
            .group_by(Lab.id)
            .order_by(Lab.title)
        )

        report: list[LabPerformance] = []
        for lab_id, slug, title, attempts, passed, average, hints in result.all():
            passed = int(passed or 0)
            report.append(
                LabPerformance(
                    lab_id=lab_id,
                    slug=slug,
                    title=title,
                    attempts=int(attempts),
                    passes=passed,
                    pass_rate=_rate(passed, int(attempts)),
                    average_score=round(float(average), 1),
                    average_hints=round(float(hints), 1),
                )
            )
        return report

    async def quiz_performance(self) -> list[QuizQuestionStat]:
        passed = func.sum(case((QuizAttempt.status == AttemptStatus.PASSED, 1), else_=0))
        result = await self.session.execute(
            select(
                Quiz.id,
                Quiz.title,
                func.count(QuizAttempt.id),
                func.coalesce(func.avg(QuizAttempt.score_percent), 0.0),
                passed,
            )
            .outerjoin(QuizAttempt, QuizAttempt.quiz_id == Quiz.id)
            .group_by(Quiz.id)
            .order_by(Quiz.title)
        )

        report: list[QuizQuestionStat] = []
        for quiz_id, title, attempts, average, passes in result.all():
            report.append(
                QuizQuestionStat(
                    quiz_id=quiz_id,
                    quiz_title=title,
                    attempts=int(attempts),
                    average_score=round(float(average), 1),
                    pass_rate=_rate(int(passes or 0), int(attempts)),
                )
            )
        return report

    # ------------------------------------------------------------------ #
    # Roster
    # ------------------------------------------------------------------ #
    async def roster(self, *, limit: int = 100, offset: int = 0) -> list[RosterEntry]:
        result = await self.session.execute(
            select(User, UserStats)
            .join(UserStats, UserStats.user_id == User.id)
            .where(User.is_active.is_(True))
            .order_by(UserStats.total_xp.desc())
            .limit(limit)
            .offset(offset)
        )
        return [
            RosterEntry(
                user_id=user.id,
                display_name=user.full_name or user.username,
                email=user.email,
                level=stats.level,
                total_xp=stats.total_xp,
                lessons_completed=stats.lessons_completed,
                labs_completed=stats.labs_completed,
                last_active_at=stats.last_activity_date,
            )
            for user, stats in result.all()
        ]
