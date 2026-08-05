"""Portable column types shared by every model.

The platform runs on SQLite in development and PostgreSQL in production, so
models must not depend on dialect-specific types. These decorators pick the
native PostgreSQL type when available and fall back to a portable
representation otherwise.
"""

from __future__ import annotations

import enum
import uuid
from typing import Any, TypeVar

from sqlalchemy import CHAR, JSON, types
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.engine.interfaces import Dialect

# JSONB on PostgreSQL (indexable, binary) and plain JSON everywhere else.
JSONColumn = JSON().with_variant(JSONB, "postgresql")

EnumT = TypeVar("EnumT", bound=enum.Enum)


def enum_column(enum_cls: type[EnumT], *, length: int = 32) -> SAEnum:
    """Build the standard enum column for this schema.

    Two deliberate departures from SQLAlchemy's defaults:

    * ``native_enum=False`` — stores a VARCHAR instead of a PostgreSQL ``ENUM``
      type. Native enums need an ``ALTER TYPE`` migration to add a single
      value and do not exist on SQLite, so avoiding them keeps the two
      dialects byte-identical.
    * ``values_callable`` — persists each member's *value* (``"student"``)
      rather than its *name* (``"STUDENT"``), which is what SQLAlchemy would
      otherwise store. Without this, raw SQL and analytics queries would see
      uppercase identifiers that disagree with every value the API emits.
    """
    return SAEnum(
        enum_cls,
        native_enum=False,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


class GUID(types.TypeDecorator[uuid.UUID]):
    """Platform-independent UUID.

    Stores a native ``UUID`` on PostgreSQL and a 36-character hyphenated string
    elsewhere. Always presents a :class:`uuid.UUID` to Python.
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PGUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value: Any, dialect: Dialect) -> Any:
        if value is None:
            return None
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(str(value))
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value: Any, dialect: Dialect) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))
