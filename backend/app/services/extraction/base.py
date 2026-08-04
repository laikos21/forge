"""Extraction contract shared by every format handler.

An extractor turns raw bytes (or pasted text) into an ordered list of
:class:`DocumentUnit` values. The normalized full text of a source is *defined*
as those units joined by a blank line, and :func:`assemble` is what computes the
character offsets. Because both sides of that relationship are produced in one
place, an excerpt offset always points at the same characters the viewer shows.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

UNIT_SEPARATOR = "\n\n"


@dataclass(slots=True)
class DocumentUnit:
    kind: str
    text: str
    title: str | None = None
    locator: dict[str, Any] = field(default_factory=dict)
    ordinal: int = 0
    char_start: int = 0
    char_end: int = 0


@dataclass(slots=True)
class ExtractedMetadata:
    title: str | None = None
    author: str | None = None
    publisher: str | None = None
    published_on: dt.date | None = None
    source_url: str | None = None
    page_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "publisher": self.publisher,
            "published_on": self.published_on.isoformat() if self.published_on else None,
            "source_url": self.source_url,
            "page_count": self.page_count,
            **({"extra": self.extra} if self.extra else {}),
        }


@dataclass(slots=True)
class ExtractionResult:
    text: str
    units: list[DocumentUnit]
    metadata: ExtractedMetadata
    method: str
    warnings: list[str] = field(default_factory=list)


class ExtractionError(RuntimeError):
    """Raised when a file cannot be parsed at all."""


def assemble(units: list[DocumentUnit], method: str, metadata: ExtractedMetadata,
             warnings: list[str] | None = None) -> ExtractionResult:
    """Number the units, compute offsets and build the canonical full text."""

    cleaned = [u for u in units if u.text.strip()] or units
    cursor = 0
    parts: list[str] = []
    for index, unit in enumerate(cleaned):
        unit.ordinal = index
        unit.char_start = cursor
        unit.char_end = cursor + len(unit.text)
        parts.append(unit.text)
        cursor = unit.char_end + len(UNIT_SEPARATOR)
    return ExtractionResult(
        text=UNIT_SEPARATOR.join(parts),
        units=cleaned,
        metadata=metadata,
        method=method,
        warnings=list(warnings or []),
    )
