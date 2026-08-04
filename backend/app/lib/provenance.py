"""Human-readable rendering of a locator.

A locator is whatever the extractor could honestly record about *where* a piece
of text came from: a PDF page, a Markdown section, a transcript timestamp, a CSV
row range, a JSON pointer. This module turns it into a short label
(``p. 12``, ``[12:30]``, ``rows 26-50``) and a full citation string.
"""

from __future__ import annotations

from typing import Any


def locator_label(locator: dict[str, Any] | None) -> str:
    locator = locator or {}
    if "page" in locator:
        return f"p. {locator['page']}"
    if "timestamp" in locator:
        return f"[{locator['timestamp']}]"
    if "timestamp_seconds" in locator:
        seconds = int(locator["timestamp_seconds"])
        return f"[{seconds // 60}:{seconds % 60:02d}]"
    if "row_start" in locator:
        end = locator.get("row_end", locator["row_start"])
        return f"rows {locator['row_start']}-{end}"
    if "row" in locator:
        return f"row {locator['row']}"
    if "section" in locator and locator["section"]:
        return f"§ {locator['section']}"
    if "pointer" in locator:
        return str(locator["pointer"])
    if "index" in locator:
        return f"record {int(locator['index']) + 1}"
    if "region" in locator:
        return str(locator["region"])
    if "block" in locator:
        return f"block {int(locator['block']) + 1}"
    if "char_start" in locator:
        return f"char {locator['char_start']}"
    return ""


def citation(
    source_title: str,
    *,
    author: str | None = None,
    published_on: str | None = None,
    locator: dict[str, Any] | None = None,
    url: str | None = None,
) -> str:
    parts = [source_title]
    if author:
        parts.append(author)
    if published_on:
        parts.append(str(published_on))
    label = locator_label(locator)
    if label:
        parts.append(label)
    text = " — ".join(parts)
    if url:
        text += f" <{url}>"
    return text


def provenance_dict(
    *,
    source_id: str,
    source_title: str,
    kind: str,
    locator: dict[str, Any] | None,
    char_start: int | None = None,
    char_end: int | None = None,
    author: str | None = None,
    published_on: str | None = None,
    url: str | None = None,
    method: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    """The provenance block attached to every derived object in the API."""

    return {
        "source_id": source_id,
        "source_title": source_title,
        "source_kind": kind,
        "locator": locator or {},
        "locator_label": locator_label(locator),
        "char_start": char_start,
        "char_end": char_end,
        "author": author,
        "published_on": published_on,
        "url": url,
        "extraction_method": method,
        "created_at": created_at,
        "citation": citation(
            source_title, author=author, published_on=published_on, locator=locator, url=url
        ),
    }
