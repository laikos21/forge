"""Entity detection and reconciliation.

Detection is deterministic and always labelled with a confidence level. Nothing
is attached to a source until the user confirms it on the review screen, because
a wrong ticker silently attached to a research note is worse than no ticker.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain import EntityKind
from ..lib.text import find_companies, find_people, find_tickers, top_keywords
from ..models import Entity, EntityMention, Source
from . import indexer

LEGAL_SUFFIX_RE = re.compile(
    r"[\s,]+(inc|inc\.|corp|corp\.|corporation|ltd|ltd\.|llc|plc|sa|s\.a\.|ag|nv|holdings)\.?$",
    re.IGNORECASE,
)


def normalize_name(name: str) -> str:
    value = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    value = LEGAL_SUFFIX_RE.sub("", value.strip())
    value = re.sub(r"[^\w\s&-]", "", value)
    return re.sub(r"\s+", " ", value).strip().lower()


@dataclass(slots=True)
class EntityCandidate:
    kind: str
    name: str
    confidence: str
    count: int
    detector: str
    existing_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def detect_candidates(session: Session, text: str, metadata: dict[str, Any] | None = None) -> list[EntityCandidate]:
    metadata = metadata or {}
    candidates: list[EntityCandidate] = []

    for symbol, count, confidence in find_tickers(text):
        candidates.append(
            EntityCandidate(EntityKind.TICKER, symbol, confidence, count, "regex:ticker")
        )
    for name, count in find_companies(text):
        candidates.append(
            EntityCandidate(EntityKind.COMPANY, name, "medium", count, "regex:legal-suffix")
        )
    for name, count in find_people(text):
        candidates.append(EntityCandidate(EntityKind.PERSON, name, "medium", count, "regex:byline"))

    author = metadata.get("author")
    if author and isinstance(author, str) and 3 < len(author) < 120:
        candidates.append(EntityCandidate(EntityKind.PERSON, author.strip(), "high", 1, "metadata:author"))

    for word, count in top_keywords(text, limit=8, min_length=5):
        if count >= 3:
            candidates.append(EntityCandidate(EntityKind.TOPIC, word, "low", count, "frequency"))

    # De-duplicate by (kind, normalized name), keeping the highest confidence.
    rank = {"high": 3, "medium": 2, "low": 1}
    best: dict[tuple[str, str], EntityCandidate] = {}
    for candidate in candidates:
        key = (candidate.kind, normalize_name(candidate.name))
        if not key[1]:
            continue
        current = best.get(key)
        if current is None or rank[candidate.confidence] > rank[current.confidence]:
            best[key] = candidate
        elif current is not None:
            current.count = max(current.count, candidate.count)

    resolved = list(best.values())
    if resolved:
        existing = session.execute(
            select(Entity).where(
                Entity.normalized_name.in_([normalize_name(c.name) for c in resolved])
            )
        ).scalars().all()
        lookup = {(e.kind, e.normalized_name): e.id for e in existing}
        for candidate in resolved:
            candidate.existing_id = lookup.get((candidate.kind, normalize_name(candidate.name)))
            if candidate.existing_id and candidate.confidence == "low":
                candidate.confidence = "medium"

    order = {"high": 0, "medium": 1, "low": 2}
    resolved.sort(key=lambda c: (order[c.confidence], -c.count, c.name.lower()))
    return resolved


def get_or_create_entity(
    session: Session,
    kind: str,
    name: str,
    *,
    description: str | None = None,
    data: dict[str, Any] | None = None,
    is_demo: bool = False,
) -> Entity:
    kind = str(EntityKind(kind))
    name = name.strip()
    normalized = normalize_name(name)
    if not normalized:
        raise ValueError("entity name is empty after normalization")
    entity = session.execute(
        select(Entity).where(Entity.kind == kind, Entity.normalized_name == normalized)
    ).scalar_one_or_none()
    if entity is not None:
        if description and not entity.description:
            entity.description = description
        if data:
            entity.data = {**(entity.data or {}), **data}
        return entity
    entity = Entity(
        kind=kind,
        name=name.upper() if kind == EntityKind.TICKER else name,
        normalized_name=normalized,
        description=description,
        data=data or {},
        is_demo=is_demo,
    )
    session.add(entity)
    session.flush()
    indexer.index_entity(session, entity)
    return entity


def attach_entities(
    session: Session,
    source: Source,
    candidates: list[dict[str, Any]],
) -> list[Entity]:
    """Create entities and mentions for the candidates the user confirmed."""

    attached: list[Entity] = []
    for candidate in candidates:
        name = str(candidate.get("name", "")).strip()
        kind = str(candidate.get("kind", "")).strip()
        if not name or not kind:
            continue
        entity = get_or_create_entity(session, kind, name)
        mention = session.execute(
            select(EntityMention).where(
                EntityMention.entity_id == entity.id, EntityMention.source_id == source.id
            )
        ).scalar_one_or_none()
        if mention is None:
            mention = EntityMention(
                entity_id=entity.id,
                source_id=source.id,
                count=int(candidate.get("count") or 1),
                confirmed=True,
                detector=str(candidate.get("detector") or "user"),
            )
            session.add(mention)
        else:
            mention.confirmed = True
            mention.count = max(mention.count, int(candidate.get("count") or 1))
        attached.append(entity)
    session.flush()
    return attached


def entities_for_source(session: Session, source_id: str) -> list[Entity]:
    return list(
        session.execute(
            select(Entity)
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .where(EntityMention.source_id == source_id)
            .order_by(Entity.kind, Entity.name)
        ).scalars()
    )


def source_counts_by_entity(session: Session) -> dict[str, int]:
    rows = session.execute(
        select(EntityMention.entity_id, func.count(EntityMention.source_id)).group_by(
            EntityMention.entity_id
        )
    ).all()
    return {row[0]: int(row[1]) for row in rows}
