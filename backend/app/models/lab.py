"""Labs, saved topologies, and lab attempts.

Topology documents are stored as a single JSON column rather than normalised
into `devices` / `links` / `interfaces` tables. The rationale:

* The editor loads and saves a whole topology atomically — there is no query
  pattern that fetches "all routers across all users", so normalisation would
  buy nothing and cost a multi-table join on every canvas load.
* The document schema evolves quickly across Parts 4–7 (new device types, new
  per-interface configuration keys). A versioned JSON document lets us migrate
  in application code rather than with a DDL migration per change.
* `schema_version` on every document makes those migrations explicit.

The document shape itself is defined and validated by Pydantic models in
`app.schemas.topology` (Part 4), so "schemaless storage" does not mean
unvalidated input.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.db.types import GUID, JSONColumn, enum_column
from app.models.enums import AttemptStatus, Difficulty, LabKind, ScenarioType

if TYPE_CHECKING:
    from app.models.catalog import Lesson
    from app.models.user import User

# Bumped whenever the topology JSON document format changes incompatibly.
TOPOLOGY_SCHEMA_VERSION = 1


class Lab(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An authored hands-on exercise."""

    __tablename__ = "labs"

    # Labs may stand alone in the scenario library or hang off a lesson.
    lesson_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("lessons.id", ondelete="SET NULL"), index=True
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[LabKind] = mapped_column(
        enum_column(LabKind, length=20), default=LabKind.GUIDED, nullable=False
    )
    scenario_type: Mapped[ScenarioType | None] = mapped_column(
        enum_column(ScenarioType, length=20), index=True
    )
    difficulty: Mapped[Difficulty] = mapped_column(
        enum_column(Difficulty, length=20),
        default=Difficulty.BEGINNER,
        nullable=False,
    )

    # Narrative requirements shown to the student before they start.
    requirements: Mapped[list[str]] = mapped_column(JSONColumn, default=list, nullable=False)
    # Ordered checkpoints: [{id, title, hint, points}, ...]
    objectives: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )
    # Topology the student starts from (may be empty for design-from-scratch labs).
    initial_topology: Mapped[dict[str, Any]] = mapped_column(
        JSONColumn, default=dict, nullable=False
    )
    # Declarative assertions evaluated by the grader, e.g.
    # {"type": "ping", "from": "PC1", "to": "8.8.8.8", "points": 10}
    grading_rules: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )
    # Faults injected for troubleshooting labs, e.g.
    # {"type": "wrong_gateway", "target": "PC2"}
    fault_injections: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )

    estimated_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    passing_score: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    xp_reward: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    lesson: Mapped[Lesson | None] = relationship(back_populates="labs")
    attempts: Mapped[list[LabAttempt]] = relationship(
        back_populates="lab", cascade="all, delete-orphan"
    )


class LabAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One learner's run at a lab, including their working topology."""

    __tablename__ = "lab_attempts"
    __table_args__ = (Index("ix_lab_attempts_user_lab", "user_id", "lab_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    lab_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("labs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[AttemptStatus] = mapped_column(
        enum_column(AttemptStatus, length=20),
        default=AttemptStatus.IN_PROGRESS,
        nullable=False,
    )
    # The learner's live working copy, autosaved from the canvas.
    working_topology: Mapped[dict[str, Any]] = mapped_column(
        JSONColumn, default=dict, nullable=False
    )
    # Per-rule grading output: [{rule_id, passed, points, message}, ...]
    check_results: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONColumn, default=list, nullable=False
    )
    score_percent: Mapped[float | None] = mapped_column(Float)
    hints_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="lab_attempts")
    lab: Mapped[Lab] = relationship(back_populates="attempts")


class Topology(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A saved network design in the free-form topology editor."""

    __tablename__ = "topologies"
    __table_args__ = (Index("ix_topologies_owner_updated", "owner_id", "updated_at"),)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # {"schemaVersion": 1, "devices": [...], "links": [...], "groups": [...], "viewport": {...}}
    document: Mapped[dict[str, Any]] = mapped_column(JSONColumn, default=dict, nullable=False)
    schema_version: Mapped[int] = mapped_column(
        Integer, default=TOPOLOGY_SCHEMA_VERSION, nullable=False
    )
    thumbnail_url: Mapped[str | None] = mapped_column(String(512))
    # Templates authored by instructors appear in the "start from" gallery.
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    device_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    owner: Mapped[User] = relationship(back_populates="topologies")
