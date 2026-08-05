"""Aggregates every v1 endpoint module into one router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    courses,
    devices,
    gamification,
    health,
    labs,
    lessons,
    notes,
    quizzes,
    simulation,
    topologies,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(courses.router)
api_router.include_router(lessons.router)
api_router.include_router(quizzes.router)
api_router.include_router(topologies.router)
api_router.include_router(devices.router)
api_router.include_router(simulation.router)
api_router.include_router(labs.router)
api_router.include_router(gamification.router)
api_router.include_router(notes.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]
