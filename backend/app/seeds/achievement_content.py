"""Seeded achievements.

The set is chosen to reward **three different things**, because a badge list
that only rewards volume teaches people to grind:

* *progress* — getting through material at all;
* *mastery* — doing it well (a perfect lab, a passed quiz);
* *streak* — coming back, which is what actually makes the learning stick.

XP rewards are deliberately small. A badge that pays more than the work it
recognises inverts the incentive.
"""

from __future__ import annotations

from typing import Any


def _achievement(
    slug: str,
    title: str,
    description: str,
    icon: str,
    category: str,
    criteria: dict[str, Any],
    xp: int = 25,
    *,
    secret: bool = False,
) -> dict[str, Any]:
    return {
        "slug": slug,
        "title": title,
        "description": description,
        "icon": icon,
        "category": category,
        "criteria": criteria,
        "xp_reward": xp,
        "is_secret": secret,
    }


def _at_least(metric: str, value: int) -> dict[str, Any]:
    return {"metric": metric, "operator": ">=", "value": value}


ACHIEVEMENTS: list[dict[str, Any]] = [
    # -- Progress ---------------------------------------------------------- #
    _achievement(
        "first-steps",
        "First steps",
        "Complete your first lesson.",
        "footprints",
        "progress",
        _at_least("lessons_completed", 1),
        xp=10,
    ),
    _achievement(
        "getting-going",
        "Getting going",
        "Complete ten lessons.",
        "book-open",
        "progress",
        _at_least("lessons_completed", 10),
        xp=25,
    ),
    _achievement(
        "course-complete",
        "Course complete",
        "Finish a course from start to end.",
        "graduation-cap",
        "progress",
        _at_least("courses_completed", 1),
        xp=50,
    ),
    _achievement(
        "level-five",
        "Level five",
        "Reach level 5.",
        "trending-up",
        "progress",
        _at_least("level", 5),
        xp=25,
    ),
    # -- Labs -------------------------------------------------------------- #
    _achievement(
        "hands-on",
        "Hands on",
        "Pass your first hands-on lab.",
        "flask-conical",
        "lab",
        _at_least("labs_completed", 1),
        xp=25,
    ),
    _achievement(
        "lab-technician",
        "Lab technician",
        "Pass five labs.",
        "wrench",
        "lab",
        _at_least("labs_completed", 5),
        xp=50,
    ),
    _achievement(
        "network-architect",
        "Network architect",
        "Save ten of your own topologies in the designer.",
        "network",
        "lab",
        _at_least("topologies_saved", 10),
        xp=40,
    ),
    # -- Mastery ----------------------------------------------------------- #
    _achievement(
        "flawless",
        "Flawless",
        "Pass a lab with a perfect score.",
        "target",
        "mastery",
        _at_least("perfect_labs", 1),
        xp=40,
    ),
    _achievement(
        "quiz-master",
        "Quiz master",
        "Pass five quizzes.",
        "brain",
        "mastery",
        _at_least("quizzes_passed", 5),
        xp=40,
    ),
    _achievement(
        "three-perfect-labs",
        "No loose ends",
        "Pass three labs with a perfect score.",
        "award",
        "mastery",
        _at_least("perfect_labs", 3),
        xp=75,
    ),
    # -- Streaks ----------------------------------------------------------- #
    _achievement(
        "three-day-streak",
        "Three in a row",
        "Study three days running.",
        "flame",
        "streak",
        _at_least("current_streak_days", 3),
        xp=20,
    ),
    _achievement(
        "week-streak",
        "A full week",
        "Study seven days running.",
        "calendar-check",
        "streak",
        _at_least("current_streak_days", 7),
        xp=50,
    ),
    _achievement(
        "month-streak",
        "Thirty days",
        "Study thirty days running.",
        "trophy",
        "streak",
        _at_least("longest_streak_days", 30),
        xp=150,
    ),
    # -- Compound and secret ------------------------------------------------ #
    _achievement(
        "well-rounded",
        "Well rounded",
        "Complete lessons, pass quizzes, and pass labs — all three.",
        "layers",
        "mastery",
        {
            "allOf": [
                _at_least("lessons_completed", 5),
                _at_least("quizzes_passed", 2),
                _at_least("labs_completed", 2),
            ]
        },
        xp=60,
    ),
    _achievement(
        "night-shift",
        "The long haul",
        "Spend ten hours studying.",
        "moon",
        "special",
        _at_least("study_minutes", 600),
        xp=80,
        secret=True,
    ),
]
