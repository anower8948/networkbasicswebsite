"""Enumerations used across the schema.

All enums are persisted as VARCHAR via `native_enum=False` rather than as
PostgreSQL `ENUM` types. Native enums require an `ALTER TYPE` migration to add
a single value and are not supported by SQLite at all; storing strings keeps the
two dialects identical and makes adding, say, a new device category a one-line
change plus a CHECK-constraint migration.
"""

from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    """Coarse-grained authorisation role.

    Ordered by privilege; see `app.api.deps.require_role`.
    """

    STUDENT = "student"
    INSTRUCTOR = "instructor"
    ADMIN = "admin"


class TrackLevel(StrEnum):
    """The three top-level learning tracks."""

    FOUNDATION = "foundation"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class Difficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class LessonType(StrEnum):
    THEORY = "theory"
    INTERACTIVE = "interactive"
    SIMULATION = "simulation"
    LAB = "lab"
    QUIZ = "quiz"
    ASSESSMENT = "assessment"


class ProgressStatus(StrEnum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class EnrollmentStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    PAUSED = "paused"
    DROPPED = "dropped"


class QuestionType(StrEnum):
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    TRUE_FALSE = "true_false"
    FILL_BLANK = "fill_blank"
    ORDERING = "ordering"
    MATCHING = "matching"
    SUBNET_CALC = "subnet_calc"
    CLI_COMMAND = "cli_command"


class LabKind(StrEnum):
    """What a lab asks the student to do."""

    GUIDED = "guided"
    CHALLENGE = "challenge"
    TROUBLESHOOTING = "troubleshooting"
    DESIGN = "design"


class ScenarioType(StrEnum):
    """Real-world network scenarios the hands-on projects model."""

    HOME = "home"
    APARTMENT = "apartment"
    SMALL_OFFICE = "small_office"
    SCHOOL = "school"
    UNIVERSITY = "university"
    HOSPITAL = "hospital"
    BANK = "bank"
    ENTERPRISE = "enterprise"
    ISP = "isp"
    CAMPUS = "campus"
    CLOUD = "cloud"
    DATA_CENTER = "data_center"


class AttemptStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    PASSED = "passed"
    FAILED = "failed"
    ABANDONED = "abandoned"


class AchievementCategory(StrEnum):
    PROGRESS = "progress"
    MASTERY = "mastery"
    STREAK = "streak"
    LAB = "lab"
    COMMUNITY = "community"
    SPECIAL = "special"


class XPReason(StrEnum):
    """Why experience points were granted — the audit trail behind leaderboards."""

    LESSON_COMPLETED = "lesson_completed"
    QUIZ_PASSED = "quiz_passed"
    LAB_COMPLETED = "lab_completed"
    COURSE_COMPLETED = "course_completed"
    ACHIEVEMENT_EARNED = "achievement_earned"
    STREAK_BONUS = "streak_bonus"
    MANUAL_ADJUSTMENT = "manual_adjustment"


class DeviceKind(StrEnum):
    """Devices that can be placed on the topology canvas."""

    PC = "pc"
    LAPTOP = "laptop"
    SERVER = "server"
    ROUTER = "router"
    SWITCH = "switch"
    MULTILAYER_SWITCH = "multilayer_switch"
    FIREWALL = "firewall"
    WIRELESS_ROUTER = "wireless_router"
    ACCESS_POINT = "access_point"
    CLOUD = "cloud"
    ISP = "isp"
    NAS = "nas"
    PRINTER = "printer"
    CAMERA = "camera"
    IP_PHONE = "ip_phone"
    IOT = "iot"


class CableKind(StrEnum):
    """Physical media joining two interfaces."""

    STRAIGHT_THROUGH = "straight_through"
    CROSSOVER = "crossover"
    FIBER = "fiber"
    CONSOLE = "console"
    SERIAL = "serial"
    WIRELESS = "wireless"


class PortKind(StrEnum):
    """What a device interface physically is."""

    ETHERNET = "ethernet"
    FAST_ETHERNET = "fast_ethernet"
    GIGABIT_ETHERNET = "gigabit_ethernet"
    TEN_GIGABIT = "ten_gigabit"
    SERIAL = "serial"
    CONSOLE = "console"
    WIRELESS = "wireless"
    SFP = "sfp"


class TokenPurpose(StrEnum):
    """Purpose of a single-use verification token."""

    EMAIL_VERIFICATION = "email_verification"
    PASSWORD_RESET = "password_reset"
