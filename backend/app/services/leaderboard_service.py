"""Leaderboards.

Three scopes, and they are not the same query:

* **all-time** reads `user_stats.total_xp`, which is a cached sum with a
  descending index behind it — a top-50 is an index scan.
* **weekly** and **monthly** can only be answered from `xp_transactions`, by
  summing the rows in the window. This is the reason the ledger is append-only
  rather than a bare counter: "XP earned this week" is not derivable from a
  total.

Every board also carries **your own row**, even when you are nowhere near the
top. A leaderboard that only shows the top 50 tells 99% of learners nothing
about themselves.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.datetime_utils import utcnow
from app.models.user import User
from app.repositories.gamification import LeaderboardRepository
from app.schemas.gamification import Leaderboard, LeaderboardEntry
from app.services.progress_service import ProgressService

Scope = Literal["all_time", "monthly", "weekly"]

WINDOW_DAYS: dict[str, int] = {"weekly": 7, "monthly": 30}


class LeaderboardService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.board = LeaderboardRepository(session)
        self.progress = ProgressService(session)

    async def get(
        self, scope: Scope, *, viewer: User | None = None, limit: int = 50
    ) -> Leaderboard:
        entries = (
            await self._all_time(limit) if scope == "all_time" else await self._window(scope, limit)
        )

        you: LeaderboardEntry | None = None
        if viewer is not None:
            you = next((entry for entry in entries if entry.user_id == viewer.id), None)
            if you is not None:
                you = you.model_copy(update={"is_you": True})
                entries = [
                    entry.model_copy(update={"is_you": True})
                    if entry.user_id == viewer.id
                    else entry
                    for entry in entries
                ]
            else:
                you = await self._standing_of(viewer, scope)

        return Leaderboard(scope=scope, entries=entries, you=you)

    # ------------------------------------------------------------------ #
    # Scopes
    # ------------------------------------------------------------------ #
    async def _all_time(self, limit: int) -> list[LeaderboardEntry]:
        rows = await self.board.top_all_time(limit)
        return [
            self._entry(rank, user, stats.level, stats.total_xp)
            for rank, (user, stats) in enumerate(rows, start=1)
        ]

    async def _window(self, scope: Scope, limit: int) -> list[LeaderboardEntry]:
        since = utcnow() - timedelta(days=WINDOW_DAYS[scope])
        rows = await self.board.top_since(since, limit)
        return [
            self._entry(rank, user, level, int(earned))
            for rank, (user, earned, level) in enumerate(rows, start=1)
        ]

    async def _standing_of(self, viewer: User, scope: Scope) -> LeaderboardEntry:
        """The viewer's own row when they are outside the returned page.

        For a windowed board the true rank would need a full scan of everyone's
        recent XP, so rank is reported as 0 — meaning "unranked" — rather than
        paying for a number nobody is chasing. All-time rank *is* worth a count.
        """
        stats = await self.progress.stats_for(viewer)
        if scope == "all_time":
            return self._entry(
                await self.board.rank_all_time(stats.total_xp),
                viewer,
                stats.level,
                stats.total_xp,
                is_you=True,
            )

        since = utcnow() - timedelta(days=WINDOW_DAYS[scope])
        earned = await self.board.xp_since(viewer.id, since)
        return self._entry(0, viewer, stats.level, earned, is_you=True)

    @staticmethod
    def _entry(
        rank: int, user: User, level: int, xp: int, *, is_you: bool = False
    ) -> LeaderboardEntry:
        return LeaderboardEntry(
            rank=rank,
            user_id=user.id,
            # A leaderboard is public within the platform, so it shows the name
            # the learner chose to display — never their email.
            display_name=user.full_name or user.username,
            avatar_url=user.avatar_url,
            country_code=user.country,
            level=level,
            xp=xp,
            is_you=is_you,
        )
