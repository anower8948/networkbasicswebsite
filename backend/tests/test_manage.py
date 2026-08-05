"""Tests for the account administration commands.

This tool exists because Argon2 hashes cannot be read back — when the admin
password is lost there is no other honest route in. That makes it exactly the
sort of code that must not be subtly wrong: a `set-password` that silently
failed, or one that left old sessions alive, would be discovered at the worst
possible moment.

The commands open their own engine from `settings.DATABASE_URL`, so these tests
point that at a temporary file and exercise the real path rather than a stand-in.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password, verify_password
from app.manage import cmd_create_admin, cmd_list, cmd_promote, cmd_set_password
from app.models import Base
from app.models.enums import UserRole
from app.models.user import User


@pytest_asyncio.fixture
async def managed_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[str]:
    """A throwaway database the commands will find via settings."""
    path = tmp_path / "manage.db"
    url = f"sqlite+aiosqlite:///{path}"
    monkeypatch.setattr(settings, "DATABASE_URL", url)

    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield url


async def add_user(url: str, email: str, *, role: UserRole = UserRole.STUDENT) -> uuid.UUID:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        user = User(
            email=email,
            username=email.split("@")[0],
            hashed_password=hash_password("OriginalPassword1"),
            role=role,
        )
        session.add(user)
        await session.commit()
        user_id = user.id
    await engine.dispose()
    return user_id


async def load(url: str, email: str) -> User | None:
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        found = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
    await engine.dispose()
    return found


class TestListing:
    async def test_an_empty_instance_says_how_to_get_an_admin(
        self, managed_db: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert await cmd_list() == 0
        assert "first account you register" in capsys.readouterr().out

    async def test_it_points_out_when_nobody_is_an_admin(
        self, managed_db: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """The state someone hits after deleting or demoting their only admin."""
        await add_user(managed_db, "solo@example.com")

        await cmd_list()

        assert "No administrator" in capsys.readouterr().out

    async def test_it_stays_quiet_when_an_admin_exists(
        self, managed_db: str, capsys: pytest.CaptureFixture[str]
    ) -> None:
        await add_user(managed_db, "boss@example.com", role=UserRole.ADMIN)

        await cmd_list()

        assert "No administrator" not in capsys.readouterr().out


class TestPromote:
    async def test_it_changes_the_role(self, managed_db: str) -> None:
        await add_user(managed_db, "learner@example.com")

        assert await cmd_promote("learner@example.com", "admin") == 0

        user = await load(managed_db, "learner@example.com")
        assert user is not None
        assert user.role is UserRole.ADMIN

    async def test_a_username_works_as_well_as_an_email(self, managed_db: str) -> None:
        await add_user(managed_db, "byname@example.com")

        assert await cmd_promote("byname", "instructor") == 0

        user = await load(managed_db, "byname@example.com")
        assert user is not None
        assert user.role is UserRole.INSTRUCTOR

    async def test_an_unknown_account_fails_rather_than_pretending(self, managed_db: str) -> None:
        assert await cmd_promote("ghost@example.com", "admin") == 1


class TestSetPassword:
    async def test_the_new_password_verifies_and_the_old_one_does_not(
        self, managed_db: str
    ) -> None:
        await add_user(managed_db, "reset@example.com")

        assert await cmd_set_password("reset@example.com", "ReplacementPassword1") == 0

        user = await load(managed_db, "reset@example.com")
        assert user is not None
        assert verify_password("ReplacementPassword1", user.hashed_password)
        assert not verify_password("OriginalPassword1", user.hashed_password)

    async def test_it_signs_every_existing_session_out(self, managed_db: str) -> None:
        """Matching the in-app change: a reset must not leave old tokens live."""
        await add_user(managed_db, "sessions@example.com")
        before = await load(managed_db, "sessions@example.com")
        assert before is not None and before.tokens_valid_from is None

        await cmd_set_password("sessions@example.com", "ReplacementPassword1")

        after = await load(managed_db, "sessions@example.com")
        assert after is not None
        assert after.tokens_valid_from is not None

    async def test_a_short_password_is_refused(self, managed_db: str) -> None:
        await add_user(managed_db, "short@example.com")

        assert await cmd_set_password("short@example.com", "abc") == 1

        user = await load(managed_db, "short@example.com")
        assert user is not None
        # The original must survive a rejected change.
        assert verify_password("OriginalPassword1", user.hashed_password)

    async def test_an_unknown_account_fails(self, managed_db: str) -> None:
        assert await cmd_set_password("ghost@example.com", "LongEnoughPassword1") == 1


class TestCreateAdmin:
    async def test_it_creates_a_usable_administrator(self, managed_db: str) -> None:
        assert await cmd_create_admin("new@example.com", None, "FreshPassword2026") == 0

        user = await load(managed_db, "new@example.com")
        assert user is not None
        assert user.role is UserRole.ADMIN
        assert user.is_active
        # Created by someone with server access; there is nobody to mail.
        assert user.is_email_verified
        assert verify_password("FreshPassword2026", user.hashed_password)

    async def test_it_promotes_rather_than_duplicating_an_existing_account(
        self, managed_db: str
    ) -> None:
        """The unique index would reject a second row; promoting is what was meant."""
        await add_user(managed_db, "already@example.com")

        assert await cmd_create_admin("already@example.com", None, "FreshPassword2026") == 0

        user = await load(managed_db, "already@example.com")
        assert user is not None
        assert user.role is UserRole.ADMIN
        # The existing password is left alone — promoting is not a reset.
        assert verify_password("OriginalPassword1", user.hashed_password)
