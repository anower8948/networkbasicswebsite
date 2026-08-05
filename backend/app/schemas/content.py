"""Lesson content blocks.

A lesson body is an ordered list of typed blocks, stored as JSON and validated
here as a **discriminated union** on `type`. Two consequences:

* Authors cannot persist a malformed block — a `code` block without a language
  or a `table` whose rows do not match its headers is rejected at write time,
  not discovered by a reader months later.
* No author-supplied HTML is ever stored, so the renderer stays in control of
  presentation and there is nothing to sanitise on the way out.

Adding a block type means adding a model here, adding it to `ContentBlock`, and
adding a renderer case in `frontend/src/features/learning/components/blocks/`.
The TypeScript union mirrors this file exactly.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BlockBase(BaseModel):
    """Blocks are stored verbatim, so unknown keys are rejected rather than
    silently persisted and lost on the next edit."""

    model_config = ConfigDict(extra="forbid")


class HeadingBlock(BlockBase):
    type: Literal["heading"] = "heading"
    # h1 is the lesson title, rendered by the page shell — bodies start at h2.
    level: Literal[2, 3, 4] = 2
    text: str = Field(min_length=1, max_length=300)


class ParagraphBlock(BlockBase):
    type: Literal["paragraph"] = "paragraph"
    text: str = Field(min_length=1, max_length=8000)


class ListBlock(BlockBase):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[str] = Field(min_length=1, max_length=60)


class CalloutBlock(BlockBase):
    """An aside: a tip, a warning, or an exam-relevant note."""

    type: Literal["callout"] = "callout"
    variant: Literal["note", "tip", "warning", "important", "exam"] = "note"
    title: str | None = Field(default=None, max_length=160)
    text: str = Field(min_length=1, max_length=4000)


class CodeBlock(BlockBase):
    """A command transcript or configuration excerpt."""

    type: Literal["code"] = "code"
    # `cisco` renders with IOS-aware highlighting in the viewer.
    language: Literal["cisco", "bash", "python", "text", "json"] = "text"
    code: str = Field(min_length=1, max_length=12000)
    caption: str | None = Field(default=None, max_length=300)


class TableBlock(BlockBase):
    type: Literal["table"] = "table"
    headers: list[str] = Field(min_length=1, max_length=10)
    rows: list[list[str]] = Field(min_length=1, max_length=100)
    caption: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _rows_match_headers(self) -> TableBlock:
        width = len(self.headers)
        for index, row in enumerate(self.rows):
            if len(row) != width:
                raise ValueError(
                    f"Row {index} has {len(row)} cells but the table has {width} columns."
                )
        return self


class ImageBlock(BlockBase):
    type: Literal["image"] = "image"
    url: str = Field(min_length=1, max_length=1000)
    # Required, not optional: a decorative-only diagram in a networking course
    # is rare, and an unlabelled one is unusable with a screen reader.
    alt: str = Field(min_length=1, max_length=500)
    caption: str | None = Field(default=None, max_length=300)


class DefinitionsBlock(BlockBase):
    """A term/definition list — the shape most networking glossaries take."""

    type: Literal["definitions"] = "definitions"
    items: list[DefinitionItem] = Field(min_length=1, max_length=40)


class DefinitionItem(BlockBase):
    term: str = Field(min_length=1, max_length=160)
    definition: str = Field(min_length=1, max_length=2000)


class DividerBlock(BlockBase):
    type: Literal["divider"] = "divider"


class InteractiveBlock(BlockBase):
    """An embedded interactive widget.

    `widget` names a component the viewer knows how to render; `config` is
    passed to it. Keeping the catalogue closed (a `Literal`) means a lesson can
    never reference a widget that does not exist.
    """

    type: Literal["interactive"] = "interactive"
    widget: Literal["osi-stack", "subnet-calculator", "ipv4-anatomy", "tcp-handshake"]
    title: str | None = Field(default=None, max_length=200)
    config: dict[str, object] = Field(default_factory=dict)


# The discriminated union. Pydantic selects the model from `type`, so a bad
# block reports "unknown type" rather than a confusing cascade of field errors.
ContentBlock = Annotated[
    HeadingBlock
    | ParagraphBlock
    | ListBlock
    | CalloutBlock
    | CodeBlock
    | TableBlock
    | ImageBlock
    | DefinitionsBlock
    | DividerBlock
    | InteractiveBlock,
    Field(discriminator="type"),
]


class ContentDocument(BaseModel):
    """Validates a whole lesson body.

    Used by the seeder and by the admin content API in Part 9.
    """

    blocks: list[ContentBlock]


def validate_blocks(raw: list[dict[str, object]]) -> list[dict[str, object]]:
    """Validate untrusted blocks and return them normalised for storage."""
    document = ContentDocument(blocks=raw)
    return [block.model_dump(mode="json") for block in document.blocks]


DefinitionsBlock.model_rebuild()
