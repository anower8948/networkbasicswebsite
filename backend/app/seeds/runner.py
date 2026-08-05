"""Idempotent catalogue seeding.

Run with:

    python -m app.seeds

Upserts by slug, so re-running after editing content updates rows in place
rather than duplicating them — and never touches learner progress, which is
keyed on the ids this preserves.

Content blocks pass through `validate_blocks`, so a malformed lesson fails the
seed loudly instead of reaching the viewer.
"""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.models.catalog import Course, Lesson, Module, Quiz, QuizOption, QuizQuestion, Track
from app.models.enums import (
    AchievementCategory,
    Difficulty,
    LabKind,
    LessonType,
    QuestionType,
    ScenarioType,
    TrackLevel,
)
from app.models.gamification import Achievement
from app.models.lab import Lab
from app.schemas.content import validate_blocks
from app.schemas.gamification import AchievementCriteria
from app.schemas.lab import LabWrite
from app.seeds.achievement_content import ACHIEVEMENTS
from app.seeds.foundation_content import (
    FOUNDATION_COURSES,
    FOUNDATION_TRACK,
    PLACEHOLDER_TRACKS,
)
from app.seeds.lab_content import LABS

_CRITERIA: TypeAdapter[AchievementCriteria] = TypeAdapter(AchievementCriteria)

logger = get_logger(__name__)


async def _upsert_track(session: AsyncSession, data: dict[str, Any]) -> Track:
    result = await session.execute(select(Track).where(Track.slug == data["slug"]))
    track = result.scalar_one_or_none()

    if track is None:
        track = Track(slug=data["slug"])
        session.add(track)

    track.title = data["title"]
    track.description = data.get("description")
    track.level = TrackLevel(data["level"])
    track.icon = data.get("icon")
    track.accent_color = data.get("accent_color")
    track.order_index = data.get("order_index", 0)
    track.is_published = data.get("is_published", False)

    await session.flush()
    return track


async def _upsert_course(session: AsyncSession, track: Track, data: dict[str, Any]) -> Course:
    result = await session.execute(select(Course).where(Course.slug == data["slug"]))
    course = result.scalar_one_or_none()

    if course is None:
        course = Course(slug=data["slug"])
        session.add(course)

    course.track_id = track.id
    course.title = data["title"]
    course.summary = data.get("summary")
    course.description = data.get("description")
    course.difficulty = Difficulty(data.get("difficulty", "beginner"))
    course.estimated_minutes = data.get("estimated_minutes", 0)
    course.tags = data.get("tags", [])
    course.prerequisites = data.get("prerequisites", [])
    course.order_index = data.get("order_index", 0)
    course.is_published = data.get("is_published", False)
    course.grants_certificate = data.get("grants_certificate", False)

    await session.flush()
    return course


async def _upsert_module(session: AsyncSession, course: Course, data: dict[str, Any]) -> Module:
    result = await session.execute(
        select(Module).where(Module.course_id == course.id, Module.slug == data["slug"])
    )
    module = result.scalar_one_or_none()

    if module is None:
        module = Module(course_id=course.id, slug=data["slug"])
        session.add(module)

    module.title = data["title"]
    module.description = data.get("description")
    module.order_index = data.get("order_index", 0)

    await session.flush()
    return module


async def _upsert_lesson(session: AsyncSession, module: Module, data: dict[str, Any]) -> Lesson:
    result = await session.execute(
        select(Lesson).where(Lesson.module_id == module.id, Lesson.slug == data["slug"])
    )
    lesson = result.scalar_one_or_none()

    if lesson is None:
        lesson = Lesson(module_id=module.id, slug=data["slug"])
        session.add(lesson)

    lesson.title = data["title"]
    lesson.summary = data.get("summary")
    lesson.lesson_type = LessonType(data.get("lesson_type", "theory"))
    # A malformed block fails the seed rather than reaching a reader.
    lesson.content_blocks = validate_blocks(data.get("content_blocks", []))
    lesson.objectives = data.get("objectives", [])
    lesson.estimated_minutes = data.get("estimated_minutes", 10)
    lesson.xp_reward = data.get("xp_reward", 10)
    lesson.order_index = data.get("order_index", 0)
    lesson.is_published = data.get("is_published", True)

    await session.flush()
    return lesson


async def _upsert_quiz(session: AsyncSession, lesson: Lesson, data: dict[str, Any]) -> Quiz:
    """Replace a lesson's quiz.

    Questions are deleted and rebuilt rather than diffed: they have no stable
    external key, and `quiz_attempts` stores its own copy of the responses, so
    past attempts survive the rebuild.
    """
    result = await session.execute(
        select(Quiz).options(selectinload(Quiz.questions)).where(Quiz.lesson_id == lesson.id)
    )
    quiz = result.scalar_one_or_none()

    if quiz is None:
        quiz = Quiz(lesson_id=lesson.id)
        session.add(quiz)
    else:
        for question in list(quiz.questions):
            await session.delete(question)
        await session.flush()

    quiz.title = data["title"]
    quiz.instructions = data.get("instructions")
    quiz.passing_score = data.get("passing_score", 70)
    quiz.max_attempts = data.get("max_attempts")
    quiz.time_limit_seconds = data.get("time_limit_seconds")
    quiz.shuffle_questions = data.get("shuffle_questions", True)
    await session.flush()

    for index, question_data in enumerate(data.get("questions", [])):
        question = QuizQuestion(
            quiz_id=quiz.id,
            prompt=question_data["prompt"],
            question_type=QuestionType(question_data["question_type"]),
            explanation=question_data.get("explanation"),
            answer_key=question_data.get("answer_key"),
            media_url=question_data.get("media_url"),
            points=question_data.get("points", 1),
            order_index=index,
        )
        session.add(question)
        await session.flush()

        for option_index, option_data in enumerate(question_data.get("options", [])):
            session.add(
                QuizOption(
                    question_id=question.id,
                    text=option_data["text"],
                    is_correct=option_data.get("is_correct", False),
                    order_index=option_index,
                )
            )

    await session.flush()
    return quiz


async def _upsert_lab(session: AsyncSession, data: dict[str, Any]) -> Lab:
    """Upsert one lab, validating its authoring document first.

    Every lab passes through `LabWrite`, so a malformed grading rule or a fault
    naming a device that is not in the topology fails the seed rather than
    reaching a student mid-attempt.
    """
    payload = LabWrite.model_validate({**data, "isPublished": True})

    result = await session.execute(select(Lab).where(Lab.slug == payload.slug))
    lab = result.scalar_one_or_none()
    if lab is None:
        lab = Lab(slug=payload.slug)
        session.add(lab)

    lab.title = payload.title
    lab.description = payload.description
    lab.kind = LabKind(payload.kind)
    lab.scenario_type = ScenarioType(payload.scenario_type) if payload.scenario_type else None
    lab.difficulty = Difficulty(payload.difficulty)
    lab.requirements = list(payload.requirements)
    lab.objectives = [item.model_dump(mode="json", by_alias=True) for item in payload.objectives]
    lab.initial_topology = payload.initial_topology.model_dump(mode="json", by_alias=True)
    lab.grading_rules = [
        rule.model_dump(mode="json", by_alias=True) for rule in payload.grading_rules
    ]
    lab.fault_injections = [
        fault.model_dump(mode="json", by_alias=True) for fault in payload.fault_injections
    ]
    lab.estimated_minutes = payload.estimated_minutes
    lab.time_limit_seconds = payload.time_limit_seconds
    lab.passing_score = payload.passing_score
    lab.xp_reward = payload.xp_reward
    lab.is_published = True

    await session.flush()
    return lab


async def _upsert_achievement(session: AsyncSession, data: dict[str, Any]) -> Achievement:
    """Upsert one badge, validating its criteria document.

    A badge whose criteria name a metric the engine does not know would silently
    never award itself. Validating here turns that into a failed seed.
    """
    criteria = _CRITERIA.validate_python(data["criteria"])

    result = await session.execute(select(Achievement).where(Achievement.slug == data["slug"]))
    achievement = result.scalar_one_or_none()
    if achievement is None:
        achievement = Achievement(slug=data["slug"])
        session.add(achievement)

    achievement.title = data["title"]
    achievement.description = data["description"]
    achievement.icon = data.get("icon")
    achievement.category = AchievementCategory(data["category"])
    achievement.criteria = criteria.model_dump(mode="json", by_alias=True)
    achievement.xp_reward = data.get("xp_reward", 0)
    achievement.is_secret = data.get("is_secret", False)
    achievement.is_active = True

    await session.flush()
    return achievement


async def seed(session: AsyncSession) -> dict[str, int]:
    """Seed the catalogue. Returns a count of what was written."""
    counts = {
        "tracks": 0,
        "courses": 0,
        "modules": 0,
        "lessons": 0,
        "quizzes": 0,
        "labs": 0,
        "achievements": 0,
    }

    track = await _upsert_track(session, FOUNDATION_TRACK)
    counts["tracks"] += 1

    for placeholder in PLACEHOLDER_TRACKS:
        await _upsert_track(session, placeholder)
        counts["tracks"] += 1

    for course_data in FOUNDATION_COURSES:
        course = await _upsert_course(session, track, course_data)
        counts["courses"] += 1

        for module_data in course_data.get("modules", []):
            module = await _upsert_module(session, course, module_data)
            counts["modules"] += 1

            for lesson_data in module_data.get("lessons", []):
                lesson = await _upsert_lesson(session, module, lesson_data)
                counts["lessons"] += 1

                if "quiz" in lesson_data:
                    await _upsert_quiz(session, lesson, lesson_data["quiz"])
                    counts["quizzes"] += 1

    for lab_data in LABS:
        await _upsert_lab(session, lab_data)
        counts["labs"] += 1

    for achievement_data in ACHIEVEMENTS:
        await _upsert_achievement(session, achievement_data)
        counts["achievements"] += 1

    await session.commit()
    return counts


async def main() -> None:
    configure_logging()
    engine = create_async_engine(settings.DATABASE_URL)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        counts = await seed(session)

    await engine.dispose()
    summary = ", ".join(f"{value} {key}" for key, value in counts.items())
    logger.info("Catalogue seeded: %s", summary)
    print(f"Catalogue seeded: {summary}")


if __name__ == "__main__":
    asyncio.run(main())
