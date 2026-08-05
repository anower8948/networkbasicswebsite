"""ORM models.

Importing this package registers every mapper on `Base.metadata`. Alembic's
`env.py` and the test fixtures rely on that side effect, so all model modules
must be imported here even when nothing references them directly.
"""

from app.db.base import Base
from app.models.catalog import Course, Lesson, Module, Quiz, QuizOption, QuizQuestion, Track
from app.models.gamification import (
    Achievement,
    Certificate,
    UserAchievement,
    XPTransaction,
)
from app.models.lab import Lab, LabAttempt, Topology
from app.models.progress import (
    Bookmark,
    Enrollment,
    LessonProgress,
    Note,
    QuizAttempt,
)
from app.models.user import RefreshToken, User, UserStats, VerificationToken

__all__ = [
    "Achievement",
    "Base",
    "Bookmark",
    "Certificate",
    "Course",
    "Enrollment",
    "Lab",
    "LabAttempt",
    "Lesson",
    "LessonProgress",
    "Module",
    "Note",
    "Quiz",
    "QuizAttempt",
    "QuizOption",
    "QuizQuestion",
    "RefreshToken",
    "Topology",
    "Track",
    "User",
    "UserAchievement",
    "UserStats",
    "VerificationToken",
    "XPTransaction",
]
