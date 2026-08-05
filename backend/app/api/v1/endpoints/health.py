"""Liveness and readiness probes.

Azure App Service, Docker health checks, and Kubernetes all need a cheap
endpoint that does not touch the database (`/health`) plus one that verifies
downstream dependencies (`/health/ready`).
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.api.deps import DbSession
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.common import HealthResponse

router = APIRouter(tags=["System"])
logger = get_logger(__name__)

API_VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse, summary="Liveness probe")
async def health() -> HealthResponse:
    """Confirms the process is up. Never touches the database."""
    return HealthResponse(
        status="ok",
        version=API_VERSION,
        environment=settings.ENVIRONMENT,
        database="not_checked",
    )


@router.get("/health/ready", response_model=HealthResponse, summary="Readiness probe")
async def readiness(session: DbSession, response: Response) -> HealthResponse:
    """Confirms the database is reachable.

    Returns 503 rather than raising, so the orchestrator sees an unhealthy
    instance instead of a 500 that would be logged as an application error.
    """
    database = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 — any failure means "not ready"
        logger.error("Readiness check failed", extra={"error": str(exc)})
        database = "unavailable"
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return HealthResponse(
        status="ok" if database == "ok" else "degraded",
        version=API_VERSION,
        environment=settings.ENVIRONMENT,
        database=database,
    )
