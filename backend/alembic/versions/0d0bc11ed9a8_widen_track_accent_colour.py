"""Widen tracks.accent_color from 20 to 64 characters.

The column held a CSS custom-property reference such as
`var(--color-track-intermediate)` — 31 characters against a 20-character limit.
SQLite ignores `VARCHAR` length entirely, so development never noticed;
PostgreSQL enforces it, and seeding a production database failed outright.

Found by running the test suite against PostgreSQL in CI (Part 10), which is
the reason that matrix exists.

Revision ID: 0d0bc11ed9a8
Revises: 22095d70a020
Create Date: 2026-08-05 23:46:38.184559
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0d0bc11ed9a8"
down_revision: str | None = "22095d70a020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# SQLite has no `ALTER COLUMN`. `batch_alter_table` copies the table, applies
# the change, and swaps it — and is a plain passthrough on PostgreSQL, so one
# migration serves both dialects. Every future type change needs the same
# treatment; a bare `op.alter_column` here breaks development on SQLite.
def upgrade() -> None:
    with op.batch_alter_table("tracks") as batch:
        batch.alter_column(
            "accent_color",
            existing_type=sa.VARCHAR(length=20),
            type_=sa.String(length=64),
            existing_nullable=True,
        )


def downgrade() -> None:
    # Widening is safe to reverse only while no stored value exceeds 20
    # characters; the seeded tracks all do, so a downgrade truncates them.
    with op.batch_alter_table("tracks") as batch:
        batch.alter_column(
            "accent_color",
            existing_type=sa.String(length=64),
            type_=sa.VARCHAR(length=20),
            existing_nullable=True,
        )
