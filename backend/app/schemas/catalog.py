"""Course catalogue read models.

Three projection depths, so a request never carries more than it needs:

* ``*Summary`` — card-sized, for listings.
* ``CourseDetail`` — the syllabus: modules and lesson headers, no bodies.
* ``LessonDetail`` — one lesson including its content blocks.

Loading full lesson bodies into a course page would send hundreds of kilobytes
of prose to render a table of contents.
"""

from __future__ import annotations

import uuid

from app.models.enums import Difficulty, LessonType, ProgressStatus, TrackLevel
from app.schemas.common import APIModel
from app.schemas.content import ContentBlock


class TrackSummary(APIModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    level: TrackLevel
    icon: str | None
    accent_color: str | None
    order_index: int
    course_count: int = 0


class CourseSummary(APIModel):
    id: uuid.UUID
    track_id: uuid.UUID
    slug: str
    title: str
    summary: str | None
    difficulty: Difficulty
    estimated_minutes: int
    cover_image_url: str | None
    tags: list[str]
    order_index: int
    lesson_count: int = 0
    # On the summary as well as the detail: the certificates page needs to know
    # which finished courses have something to claim, and it only ever loads
    # enrolments — not every course in full.
    grants_certificate: bool = False
    # Present only for an authenticated learner who is enrolled.
    progress_percent: float | None = None
    is_enrolled: bool = False


class TrackWithCourses(TrackSummary):
    courses: list[CourseSummary] = []


class LessonSummary(APIModel):
    """A lesson header — enough for a syllabus row, without the body."""

    id: uuid.UUID
    slug: str
    title: str
    summary: str | None
    lesson_type: LessonType
    estimated_minutes: int
    xp_reward: int
    order_index: int
    has_quiz: bool = False
    # Present only for an authenticated learner.
    status: ProgressStatus | None = None


class ModuleSummary(APIModel):
    id: uuid.UUID
    slug: str
    title: str
    description: str | None
    order_index: int
    lessons: list[LessonSummary] = []


class CourseDetail(APIModel):
    id: uuid.UUID
    track_id: uuid.UUID
    slug: str
    title: str
    summary: str | None
    description: str | None
    difficulty: Difficulty
    estimated_minutes: int
    cover_image_url: str | None
    tags: list[str]
    prerequisites: list[str]
    grants_certificate: bool
    modules: list[ModuleSummary] = []

    lesson_count: int = 0
    is_enrolled: bool = False
    progress_percent: float = 0.0
    completed_lesson_count: int = 0
    # Where "Continue" should send the learner: the first unfinished lesson.
    next_lesson_id: uuid.UUID | None = None


class LessonNeighbour(APIModel):
    """Adjacent lesson, for previous/next navigation within a course."""

    id: uuid.UUID
    slug: str
    title: str


class LessonDetail(APIModel):
    id: uuid.UUID
    module_id: uuid.UUID
    course_id: uuid.UUID
    course_slug: str
    course_title: str
    module_title: str
    slug: str
    title: str
    summary: str | None
    lesson_type: LessonType
    objectives: list[str]
    content_blocks: list[ContentBlock]
    estimated_minutes: int
    xp_reward: int
    order_index: int

    has_quiz: bool = False
    quiz_id: uuid.UUID | None = None

    status: ProgressStatus = ProgressStatus.NOT_STARTED
    last_block_index: int = 0
    previous_lesson: LessonNeighbour | None = None
    next_lesson: LessonNeighbour | None = None
