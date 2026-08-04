"""Full-text search over the FTS5 index, plus the optional semantic adapter.

Query language (deliberately small and fully documented in the UI):

* ``breakout base``      - both words must appear
* ``"volume dry up"``    - exact phrase
* ``breakout -crypto``   - exclude a word
* ``semis*``             - prefix match
* ``title:nvidia``       - restrict a term to the title column

The user's raw input is never passed to SQLite. Every token is re-quoted before
it reaches ``MATCH``, so a stray ``"`` or ``NEAR(`` produces zero results
instead of a 500.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text as sql
from sqlalchemy.orm import Session

from ..domain import TargetType

#: Delimiters wrapped around matched terms in snippets. Control characters are
#: used so they can never collide with document content; the frontend splits on
#: them and renders <mark> without any HTML parsing.
HL_START = "\x1f"
HL_END = "\x1e"

TOKEN_RE = re.compile(r'(-?)(?:"([^"]*)"|(\S+))')
COLUMNS = ("ref_type", "ref_id", "source_id", "kind", "title", "body")
BODY_COLUMN = COLUMNS.index("body")


class SearchQueryError(ValueError):
    """Raised when a query cannot produce a valid MATCH expression."""


@dataclass(slots=True)
class ParsedQuery:
    match: str
    terms: list[str] = field(default_factory=list)
    phrases: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)


def _quote(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def parse_query(raw: str) -> ParsedQuery:
    raw = (raw or "").strip()
    if not raw:
        raise SearchQueryError("empty query")

    positives: list[str] = []
    negatives: list[str] = []
    terms: list[str] = []
    phrases: list[str] = []
    excluded: list[str] = []

    for match in TOKEN_RE.finditer(raw):
        negated = match.group(1) == "-"
        phrase = match.group(2)
        bare = match.group(3)

        if phrase is not None:
            value = phrase.strip()
            if not value:
                continue
            expression = _quote(value)
            (excluded if negated else phrases).append(value)
        else:
            value = (bare or "").strip()
            if not value:
                continue
            column = None
            if ":" in value:
                head, _, tail = value.partition(":")
                if head.lower() in {"title", "body"} and tail:
                    column, value = head.lower(), tail
            prefix = value.endswith("*")
            value = value.rstrip("*")
            value = re.sub(r"[^\w\sÀ-ÿ'&$.-]", " ", value).strip()
            if not value:
                continue
            expression = _quote(value) + ("*" if prefix else "")
            if column:
                expression = f"{column} : {expression}"
            (excluded if negated else terms).append(value)

        (negatives if negated else positives).append(expression)

    if not positives:
        if negatives:
            raise SearchQueryError("a query needs at least one term that is not excluded")
        raise SearchQueryError("no searchable terms found")

    match_expression = " AND ".join(positives)
    if negatives:
        match_expression += " NOT " + " NOT ".join(negatives)
    return ParsedQuery(match=match_expression, terms=terms, phrases=phrases, excluded=excluded)


@dataclass(slots=True)
class SearchHit:
    ref_type: str
    ref_id: str
    source_id: str | None
    kind: str
    title: str
    snippet: str
    score: float


def search_index(
    session: Session,
    query: str,
    *,
    ref_types: list[str] | None = None,
    source_ids: list[str] | None = None,
    kinds: list[str] | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SearchHit], int]:
    parsed = parse_query(query)
    where = ["search_index MATCH :match"]
    params: dict[str, Any] = {"match": parsed.match}

    if ref_types:
        placeholders = ", ".join(f":rt{i}" for i in range(len(ref_types)))
        where.append(f"ref_type IN ({placeholders})")
        params.update({f"rt{i}": str(v) for i, v in enumerate(ref_types)})
    if source_ids:
        placeholders = ", ".join(f":sid{i}" for i in range(len(source_ids)))
        where.append(f"source_id IN ({placeholders})")
        params.update({f"sid{i}": v for i, v in enumerate(source_ids)})
    if kinds:
        placeholders = ", ".join(f":k{i}" for i in range(len(kinds)))
        where.append(f"kind IN ({placeholders})")
        params.update({f"k{i}": v for i, v in enumerate(kinds)})

    clause = " AND ".join(where)
    total = int(
        session.execute(sql(f"SELECT count(*) FROM search_index WHERE {clause}"), params).scalar_one()
    )

    params.update({"limit": limit, "offset": offset, "hl_start": HL_START, "hl_end": HL_END})
    rows = session.execute(
        sql(
            f"""
            SELECT ref_type, ref_id, source_id, kind, title,
                   snippet(search_index, {BODY_COLUMN}, :hl_start, :hl_end, '…', 18) AS snippet,
                   bm25(search_index, 0.0, 0.0, 0.0, 0.0, 8.0, 1.0) AS score
            FROM search_index
            WHERE {clause}
            ORDER BY score
            LIMIT :limit OFFSET :offset
            """
        ),
        params,
    ).all()

    hits = [
        SearchHit(
            ref_type=row.ref_type,
            ref_id=row.ref_id,
            source_id=row.source_id,
            kind=row.kind or "",
            title=row.title or "",
            snippet=row.snippet or "",
            score=float(row.score),
        )
        for row in rows
    ]
    return hits, total


def group_by_source(hits: list[SearchHit]) -> list[dict[str, Any]]:
    """Group hits so a source with five matching excerpts is one result block."""

    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for hit in hits:
        key = hit.source_id or f"{hit.ref_type}:{hit.ref_id}"
        if key not in groups:
            groups[key] = {
                "key": key,
                "source_id": hit.source_id,
                "best_score": hit.score,
                "hits": [],
            }
            order.append(key)
        groups[key]["hits"].append(hit)
        groups[key]["best_score"] = min(groups[key]["best_score"], hit.score)
    return [groups[key] for key in order]


def suggest_terms(session: Session, prefix: str, limit: int = 8) -> list[str]:
    """Title-prefix suggestions for the search box."""

    prefix = (prefix or "").strip()
    if len(prefix) < 2:
        return []
    try:
        parsed = parse_query(prefix + "*")
    except SearchQueryError:
        return []
    rows = session.execute(
        sql(
            "SELECT DISTINCT title FROM search_index WHERE search_index MATCH :match "
            "AND title != '' ORDER BY bm25(search_index, 0.0, 0.0, 0.0, 0.0, 8.0, 1.0) LIMIT :limit"
        ),
        {"match": parsed.match, "limit": limit},
    ).all()
    return [row.title for row in rows]


REF_TYPE_LABELS = {
    TargetType.SOURCE: "Source",
    TargetType.EXCERPT: "Excerpt",
    TargetType.KNOWLEDGE: "Knowledge",
    TargetType.DOSSIER: "Dossier",
    TargetType.ENTITY: "Entity",
}
