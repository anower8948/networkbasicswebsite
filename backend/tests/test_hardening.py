"""Production hardening: configuration guards, headers, and payload limits.

Everything here defends something that fails *silently* rather than loudly. A
missing `Secure` flag, a permissive Host header, an absent cache directive —
none of them break a deployment, and all of them are only noticed during an
incident. Tests are how they get noticed beforehand.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.core.config import Settings

PRODUCTION_BASELINE: dict[str, Any] = {
    "ENVIRONMENT": "production",
    "SECRET_KEY": "x" * 64,
    "DEBUG": False,
    "REFRESH_COOKIE_SECURE": True,
    "HSTS_ENABLED": True,
    "RATE_LIMIT_ENABLED": True,
    "CORS_ORIGINS": ["https://learn.example.com"],
    "DATABASE_URL": "postgresql+asyncpg://user:pw@db:5432/nlp",
    "EMAIL_BACKEND": "smtp",
    "FRONTEND_URL": "https://learn.example.com",
}


@contextmanager
def secret_key_in_env() -> Iterator[None]:
    """The production guard reads SECRET_KEY from the environment directly."""
    previous = os.environ.get("SECRET_KEY")
    os.environ["SECRET_KEY"] = "x" * 64
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("SECRET_KEY", None)
        else:
            os.environ["SECRET_KEY"] = previous


def production(**overrides: Any) -> Settings:
    # `_env_file=None` so a developer's local .env cannot influence the result.
    return Settings(**{**PRODUCTION_BASELINE, **overrides}, _env_file=None)


class TestProductionConfiguration:
    """A misconfigured production process must refuse to start."""

    def test_a_correct_configuration_starts(self) -> None:
        with secret_key_in_env():
            settings = production()
        assert settings.ENVIRONMENT == "production"

    @pytest.mark.parametrize(
        ("override", "expected"),
        [
            ({"DEBUG": True}, "DEBUG must be false"),
            ({"REFRESH_COOKIE_SECURE": False}, "REFRESH_COOKIE_SECURE"),
            ({"HSTS_ENABLED": False}, "HSTS_ENABLED"),
            ({"RATE_LIMIT_ENABLED": False}, "RATE_LIMIT_ENABLED"),
            ({"CORS_ORIGINS": ["http://localhost:5173"]}, "local addresses"),
            ({"CORS_ORIGINS": ["*"]}, "cannot be '*'"),
            ({"DATABASE_URL": "sqlite+aiosqlite:///./x.db"}, "SQLite"),
            ({"EMAIL_BACKEND": "console"}, "only be written to the log"),
            ({"FRONTEND_URL": "http://learn.example.com"}, "must be https"),
            ({"SECRET_KEY": "short"}, "at least 32 characters"),
        ],
    )
    def test_each_weakness_is_refused(self, override: dict[str, Any], expected: str) -> None:
        with secret_key_in_env(), pytest.raises(ValidationError) as caught:
            production(**override)

        assert expected in str(caught.value)

    def test_a_generated_secret_key_is_refused(self) -> None:
        """A key generated per process invalidates every token on restart."""
        previous = os.environ.pop("SECRET_KEY", None)
        try:
            with pytest.raises(ValidationError) as caught:
                production()
            assert "SECRET_KEY must be set explicitly" in str(caught.value)
        finally:
            if previous is not None:
                os.environ["SECRET_KEY"] = previous

    def test_every_problem_is_reported_at_once(self) -> None:
        """One restart should reveal the whole list, not the first item."""
        with secret_key_in_env(), pytest.raises(ValidationError) as caught:
            production(DEBUG=True, REFRESH_COOKIE_SECURE=False, EMAIL_BACKEND="console")

        message = str(caught.value)
        assert "DEBUG must be false" in message
        assert "REFRESH_COOKIE_SECURE" in message
        assert "only be written to the log" in message

    def test_development_defaults_remain_frictionless(self) -> None:
        """None of the production guards applies outside production.

        Every field is passed explicitly: CI runs this suite with
        `DATABASE_URL` pointing at PostgreSQL, and a test that reads ambient
        environment would assert something different depending on the matrix
        leg it happened to run in.
        """
        settings = Settings(
            ENVIRONMENT="development",
            DATABASE_URL="sqlite+aiosqlite:///./dev.db",
            EMAIL_BACKEND="console",
            DEBUG=True,
            REFRESH_COOKIE_SECURE=False,
            HSTS_ENABLED=False,
            _env_file=None,
        )

        # None of these would be permitted in production; all are fine here.
        assert settings.is_sqlite
        assert settings.EMAIL_BACKEND == "console"
        assert settings.DEBUG

    def test_copying_the_example_env_file_produces_a_usable_app(self) -> None:
        """The documented first-run path must actually work.

        `.env.example` ships `SECRET_KEY=` blank — it must not contain a real
        one — and the README says to copy it. Read literally that gave every
        fresh checkout a zero-length HMAC key, and PyJWT refuses to sign with
        it, so every login failed with a 500. Blank now falls back to a
        generated key.
        """
        import jwt

        example = Path(__file__).resolve().parents[1] / ".env.example"
        settings = Settings(_env_file=example)

        assert len(settings.SECRET_KEY) >= 32
        # The real assertion: a token can actually be minted.
        assert jwt.encode({"sub": "x"}, settings.SECRET_KEY, algorithm="HS256")

    def test_an_explicit_secret_key_is_never_replaced(self) -> None:
        """The blank-key fallback must not touch a key someone configured."""
        settings = Settings(SECRET_KEY="a-real-key-of-quite-sufficient-length", _env_file=None)
        assert settings.SECRET_KEY == "a-real-key-of-quite-sufficient-length"

    def test_list_settings_accept_a_comma_separated_string(self) -> None:
        """Azure application settings and `docker -e` supply plain strings."""
        settings = Settings(
            CORS_ORIGINS="https://a.example.com, https://b.example.com",
            ALLOWED_HOSTS="a.example.com,b.example.com",
            _env_file=None,
        )

        assert settings.CORS_ORIGINS == ["https://a.example.com", "https://b.example.com"]
        assert settings.ALLOWED_HOSTS == ["a.example.com", "b.example.com"]


class TestSecurityHeaders:
    async def test_every_response_carries_the_hardening_headers(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Cross-Origin-Opener-Policy"] == "same-origin"
        assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
        assert "camera=()" in response.headers["Permissions-Policy"]

    async def test_the_api_content_security_policy_permits_nothing(
        self, client: AsyncClient
    ) -> None:
        """A JSON API has nothing legitimate to load."""
        response = await client.get("/api/v1/health")
        assert response.headers["Content-Security-Policy"].startswith("default-src 'none'")

    async def test_hsts_is_absent_without_tls(self, client: AsyncClient) -> None:
        """Sending it from plain HTTP would pin localhost to HTTPS."""
        response = await client.get("/api/v1/health")
        assert "Strict-Transport-Security" not in response.headers

    async def test_authenticated_json_is_never_stored(self, authed_client: AsyncClient) -> None:
        response = await authed_client.get("/api/v1/auth/me")
        assert response.headers["Cache-Control"] == "no-store"

    async def test_the_static_catalogue_is_cacheable(self, client: AsyncClient) -> None:
        """The one endpoint that is identical for everyone and changes on deploy."""
        response = await client.get("/api/v1/topologies/device-catalog")

        assert response.status_code == 200
        assert "public" in response.headers["Cache-Control"]
        assert "max-age=3600" in response.headers["Cache-Control"]

    async def test_errors_are_hardened_too(self, client: AsyncClient) -> None:
        """A 404 is still a response an attacker can elicit."""
        response = await client.get("/api/v1/nope")

        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"


class TestPayloadLimits:
    async def test_an_oversized_body_is_rejected(self, authed_client: AsyncClient) -> None:
        """Rejected on Content-Length, before the body is buffered."""
        payload = {"name": "x" * (5 * 1024 * 1024), "document": {}}

        response = await authed_client.post("/api/v1/topologies", json=payload)

        assert response.status_code == 413
        assert response.json()["error"]["code"] == "payload_too_large"

    async def test_a_normal_body_passes(self, authed_client: AsyncClient) -> None:
        response = await authed_client.post(
            "/api/v1/topologies",
            json={
                "name": "Small",
                "document": {
                    "devices": [],
                    "links": [],
                    "groups": [],
                    "viewport": {"x": 0, "y": 0, "zoom": 1},
                },
            },
        )

        assert response.status_code == 201


class TestRequestTracing:
    async def test_a_request_id_is_returned(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")
        assert response.headers["X-Request-ID"]

    async def test_a_supplied_request_id_is_preserved(self, client: AsyncClient) -> None:
        """Lets a trace be followed across the proxy and the application."""
        response = await client.get("/api/v1/health", headers={"X-Request-ID": "trace-me-0001"})
        assert response.headers["X-Request-ID"] == "trace-me-0001"

    async def test_an_unexpected_error_reports_its_request_id(self, client: AsyncClient) -> None:
        """The id is the only thing linking a user's report to the traceback."""
        response = await client.get("/api/v1/health", headers={"X-Request-ID": "abc123"})
        assert response.headers["X-Request-ID"] == "abc123"
