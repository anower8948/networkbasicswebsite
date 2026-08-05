"""Catalogue and enrolment endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import CurrentUser, DbSession, get_optional_user
from app.models.user import User
from app.schemas.catalog import CourseDetail, TrackWithCourses
from app.schemas.common import ErrorResponse
from app.schemas.learning import EnrollmentRead, EnrollmentWithCourse
from app.services.catalog_service import CatalogService
from app.services.learning_service import LearningService

router = APIRouter(prefix="/courses", tags=["Courses"])

# The catalogue is public, but renders progress bars when a token is present.
OptionalUser = Annotated[User | None, Depends(get_optional_user)]

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
}


@router.get(
    "/tracks",
    response_model=list[TrackWithCourses],
    summary="Browse every published track and its courses",
)
async def list_tracks(session: DbSession, user: OptionalUser) -> list[TrackWithCourses]:
    """Public. Annotated with enrolment and progress for a signed-in learner."""
    return await CatalogService(session).list_tracks(user)


@router.get(
    "/enrollments",
    response_model=list[EnrollmentWithCourse],
    responses=_ERRORS,
    summary="Courses the current learner is enrolled in",
)
async def list_enrollments(session: DbSession, user: CurrentUser) -> list[EnrollmentWithCourse]:
    """The learner's own courses, each with enough course detail to render a card."""
    service = LearningService(session)
    enrollments = await service.list_enrollments(user)

    # `list_enrollments` eagerly loads `course`, so building the nested summary
    # here issues no further queries.
    lesson_counts = await service.courses.lesson_counts([item.course_id for item in enrollments])

    return [
        EnrollmentWithCourse(
            **EnrollmentRead.model_validate(item).model_dump(),
            course=CatalogService.course_summary_for(
                item.course,
                lesson_count=lesson_counts.get(item.course_id, 0),
                is_enrolled=True,
                progress_percent=item.progress_percent,
            ),
        )
        for item in enrollments
    ]


@router.get(
    "/{slug}",
    response_model=CourseDetail,
    responses=_ERRORS,
    summary="A course syllabus with the learner's progress",
)
async def get_course(slug: str, session: DbSession, user: OptionalUser) -> CourseDetail:
    return await CatalogService(session).get_course(slug, user)


@router.post(
    "/{slug}/enroll",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Enrol in a course",
)
async def enroll(slug: str, session: DbSession, user: CurrentUser) -> EnrollmentRead:
    """Idempotent — enrolling twice returns the existing enrolment."""
    enrollment = await LearningService(session).enroll(user, slug)
    return EnrollmentRead.model_validate(enrollment)
