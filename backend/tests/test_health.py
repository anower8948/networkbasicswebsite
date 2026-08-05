"""Tests for system endpoints and the error envelope."""

from __future__ import annotations

from httpx import AsyncClient


class TestHealth:
    async def test_liveness(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["database"] == "not_checked"

    async def test_readiness_checks_the_database(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health/ready")

        assert response.status_code == 200
        assert response.json()["database"] == "ok"


class TestErrorEnvelope:
    async def test_unknown_route_uses_the_standard_shape(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/does-not-exist")

        assert response.status_code == 404
        assert "error" in response.json()
        assert response.json()["error"]["code"] == "http_404"

    async def test_validation_errors_list_offending_fields(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/auth/login", json={"email": "not-an-email"})

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_error"
        assert "email" in error["details"]["fields"]
        assert "password" in error["details"]["fields"]


class TestSecurityHeaders:
    async def test_response_carries_hardening_headers(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/health")

        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-Request-ID"]
