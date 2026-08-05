"""Pytest fixtures.

By default each test runs against a fresh in-memory SQLite database.
`StaticPool` forces every connection to reuse the same underlying in-memory
database — without it, each new connection would silently get its own empty one.

Set `DATABASE_URL` to a PostgreSQL DSN to run the same suite against the dialect
production uses. CI does exactly that in a matrix, because the portable column
types in `app/db/types.py` exist to paper over differences between the two, and
an abstraction nobody exercises is an assumption. On PostgreSQL the schema is
created and dropped per test rather than living in memory.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool, StaticPool

from app.core.rate_limit import limiter
from app.db.session import get_db
from app.main import create_app
from app.models import Base

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
IS_SQLITE = TEST_DATABASE_URL.startswith("sqlite")


@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def engine() -> AsyncGenerator[Any, None]:
    """A fresh schema per test, created from the ORM metadata."""
    if IS_SQLITE:
        test_engine = create_async_engine(
            TEST_DATABASE_URL,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # A real server needs no pool tricks, but the schema is shared state,
        # so it is dropped and rebuilt around every test.
        test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)

    async with test_engine.begin() as connection:
        if not IS_SQLITE:
            await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    yield test_engine

    if not IS_SQLITE:
        async with test_engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session(engine: Any) -> AsyncGenerator[AsyncSession, None]:
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        yield db_session


@pytest_asyncio.fixture
async def client(engine: Any) -> AsyncGenerator[AsyncClient, None]:
    """An HTTP client wired to the app with the test database injected."""
    app = create_app()
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with factory() as db_session:
            try:
                yield db_session
            except Exception:
                await db_session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        follow_redirects=True,
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> None:
    """Clear rate-limit counters between tests.

    The limiter is a process-global singleton, so without this the login
    attempts in one test consume another's budget and failures appear in
    whichever test happens to run eleventh.
    """
    limiter.reset()


@pytest_asyncio.fixture
async def seeded_catalog(engine: Any) -> dict[str, int]:
    """Load the real Foundations content into the test database.

    Tests run against the same authored content that ships, so a broken lesson
    or a malformed answer key fails the suite rather than reaching a learner.
    """
    from app.seeds.runner import seed

    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as db_session:
        return await seed(db_session)


@pytest.fixture
def user_payload() -> dict[str, str]:
    return {
        "email": "learner@example.com",
        "username": "learner",
        "password": "Subnetting2024",
        "full_name": "Test Learner",
    }


@pytest_asyncio.fixture
async def authed_client(
    client: AsyncClient, user_payload: dict[str, str]
) -> AsyncGenerator[AsyncClient, None]:
    """A client that has registered and carries a valid access token."""
    response = await client.post("/api/v1/auth/register", json=user_payload)
    assert response.status_code == 201, response.text
    token = response.json()["accessToken"]
    client.headers["Authorization"] = f"Bearer {token}"
    yield client
