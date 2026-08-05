"""Shared response envelopes and base schema configuration."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

T = TypeVar("T")


class APIModel(BaseModel):
    """Base for every schema in the API.

    * `from_attributes` lets responses be built straight from ORM instances.
    * `alias_generator=to_camel` makes the wire format camelCase, which is
      idiomatic for the TypeScript client. FastAPI serialises responses with
      `by_alias=True` by default, so this applies to output automatically.
    * `populate_by_name` keeps the snake_case field name valid on *input* too,
      so both `full_name` and `fullName` are accepted from a request body.
    """

    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        str_strip_whitespace=True,
    )


class ErrorDetail(APIModel):
    code: str = Field(description="Stable machine-readable error identifier.")
    message: str = Field(description="Human-readable explanation.")
    details: dict[str, Any] | None = None


class ErrorResponse(APIModel):
    """The single error shape returned by every failing endpoint."""

    error: ErrorDetail


class Page(APIModel, Generic[T]):
    """Offset-paginated collection."""

    items: list[T]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + len(self.items) < self.total


class MessageResponse(APIModel):
    message: str


class HealthResponse(APIModel):
    status: str
    version: str
    environment: str
    database: str
