"""Dossier assembly: the research workspace around a subject."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain import TargetType
from ..lib.text import slugify
from ..models import (
    ClaimEvidence,
    Dossier,
    DossierClaim,
    DossierItem,
    Entity,
    EntityMention,
    Excerpt,
    KnowledgeObject,
    Source,
    TimelineEvent,
)
from . import indexer, links, refs, tagging

SECTIONS = ("sources", "evidence", "knowledge", "entities", "notes", "watchlist")


class DossierError(ValueError):
    pass


def unique_slug(session: Session, title: str, current_id: str | None = None) -> str:
    base = slugify(title) or "dossier"
    candidate = base
    counter = 2
    while True:
        existing = session.execute(select(Dossier).where(Dossier.slug == candidate)).scalar_one_or_none()
        if existing is None or existing.id == current_id:
            return candidate
        candidate = f"{base}-{counter}"
        counter += 1


def add_item(
    session: Session,
    dossier: Dossier,
    target_type: str,
    target_id: str,
    *,
    section: str = "sources",
    note: str | None = None,
) -> DossierItem:
    TargetType(target_type)
    if section not in SECTIONS:
        raise DossierError(f"unknown section {section!r}")
    if not refs.exists(session, target_type, target_id):
        raise DossierError(f"{target_type} {target_id} does not exist")

    existing = session.execute(
        select(DossierItem).where(
            DossierItem.dossier_id == dossier.id,
            DossierItem.target_type == target_type,
            DossierItem.target_id == target_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.section = section
        if note:
            existing.note = note
        return existing

    position = int(
        session.execute(
            select(func.coalesce(func.max(DossierItem.position), -1)).where(
                DossierItem.dossier_id == dossier.id, DossierItem.section == section
            )
        ).scalar_one()
        + 1
    )
    item = DossierItem(
        dossier_id=dossier.id,
        target_type=str(target_type),
        target_id=target_id,
        section=section,
        position=position,
        note=note,
    )
    session.add(item)
    session.flush()
    return item


def remove_item(session: Session, dossier: Dossier, item_id: str) -> bool:
    item = session.get(DossierItem, item_id)
    if item is None or item.dossier_id != dossier.id:
        return False
    session.delete(item)
    return True


def linked_source_ids(session: Session, dossier_id: str) -> list[str]:
    """Sources reachable from a dossier, directly or through a linked excerpt."""

    direct = session.execute(
        select(DossierItem.target_id).where(
            DossierItem.dossier_id == dossier_id, DossierItem.target_type == TargetType.SOURCE
        )
    ).scalars().all()
    via_excerpt = session.execute(
        select(Excerpt.source_id)
        .join(DossierItem, DossierItem.target_id == Excerpt.id)
        .where(DossierItem.dossier_id == dossier_id, DossierItem.target_type == TargetType.EXCERPT)
    ).scalars().all()
    return list(dict.fromkeys([*direct, *via_excerpt]))


def related_entities(session: Session, dossier: Dossier) -> list[dict[str, Any]]:
    """Entities explicitly attached plus entities mentioned by linked sources."""

    out: dict[str, dict[str, Any]] = {}
    explicit = session.execute(
        select(Entity)
        .join(DossierItem, DossierItem.target_id == Entity.id)
        .where(DossierItem.dossier_id == dossier.id, DossierItem.target_type == TargetType.ENTITY)
    ).scalars().all()
    for entity in explicit:
        out[entity.id] = {"id": entity.id, "kind": entity.kind, "name": entity.name, "via": "linked", "sources": 0}

    source_ids = linked_source_ids(session, dossier.id)
    if source_ids:
        rows = session.execute(
            select(Entity, func.count(EntityMention.id))
            .join(EntityMention, EntityMention.entity_id == Entity.id)
            .where(EntityMention.source_id.in_(source_ids))
            .group_by(Entity.id)
            .order_by(func.count(EntityMention.id).desc())
        ).all()
        for entity, count in rows:
            record = out.setdefault(
                entity.id,
                {"id": entity.id, "kind": entity.kind, "name": entity.name, "via": "mentioned", "sources": 0},
            )
            record["sources"] = int(count)

    if dossier.primary_entity is not None:
        primary = dossier.primary_entity
        record = out.setdefault(
            primary.id,
            {"id": primary.id, "kind": primary.kind, "name": primary.name, "via": "primary", "sources": 0},
        )
        record["via"] = "primary"
    return sorted(out.values(), key=lambda e: (e["via"] != "primary", -e["sources"], e["name"].lower()))


def detail(session: Session, dossier: Dossier) -> dict[str, Any]:
    items = sorted(dossier.items, key=lambda i: (i.section, i.position))
    resolved_items = [
        {
            "id": item.id,
            "section": item.section,
            "position": item.position,
            "note": item.note,
            **refs.describe(session, item.target_type, item.target_id).as_dict(),
        }
        for item in items
    ]

    claims: list[dict[str, Any]] = []
    for claim in sorted(dossier.claims, key=lambda c: (c.stance, c.position)):
        evidence = []
        for item in claim.evidence:
            entry: dict[str, Any] = {
                "id": item.id,
                "stance": item.stance,
                "note": item.note,
                "excerpt_id": item.excerpt_id,
                "source_id": item.source_id,
            }
            if item.excerpt_id:
                excerpt = session.get(Excerpt, item.excerpt_id)
                if excerpt is not None:
                    source = session.get(Source, excerpt.source_id)
                    entry.update(
                        {
                            "text": excerpt.text,
                            "locator": excerpt.locator,
                            "source_id": excerpt.source_id,
                            "source_title": source.title if source else None,
                        }
                    )
            elif item.source_id:
                source = session.get(Source, item.source_id)
                if source is not None:
                    entry.update({"source_title": source.title, "text": None})
            evidence.append(entry)
        claims.append(
            {
                "id": claim.id,
                "text": claim.text,
                "stance": claim.stance,
                "confidence": claim.confidence,
                "status": claim.status,
                "position": claim.position,
                "origin": claim.origin,
                "generated_by": claim.generated_by,
                "evidence": evidence,
            }
        )

    timeline = [
        {
            "id": event.id,
            "occurred_on": event.occurred_on.isoformat(),
            "title": event.title,
            "description": event.description,
            "kind": event.kind,
            "source_id": event.source_id,
            "source_title": (session.get(Source, event.source_id).title if event.source_id and session.get(Source, event.source_id) else None),
        }
        for event in sorted(dossier.events, key=lambda e: e.occurred_on)
    ]

    knowledge_ids = [i.target_id for i in items if i.target_type == TargetType.KNOWLEDGE]
    knowledge = (
        session.execute(select(KnowledgeObject).where(KnowledgeObject.id.in_(knowledge_ids))).scalars().all()
        if knowledge_ids
        else []
    )

    return {
        "items": resolved_items,
        "claims": claims,
        "timeline": timeline,
        "related_entities": related_entities(session, dossier),
        "linked_source_ids": linked_source_ids(session, dossier.id),
        "tags": [{"id": t.id, "slug": t.slug, "name": t.name, "color": t.color} for t in tagging.tags_for(session, TargetType.DOSSIER, dossier.id)],
        "links": [n.as_dict() for n in links.neighbours(session, TargetType.DOSSIER, dossier.id)],
        "knowledge_counts": {
            kind: sum(1 for k in knowledge if k.kind == kind)
            for kind in sorted({k.kind for k in knowledge})
        },
        "counts": {
            "items": len(items),
            "claims": len(claims),
            "timeline": len(timeline),
            "sources": len(linked_source_ids(session, dossier.id)),
        },
    }


def reindex(session: Session, dossier: Dossier) -> None:
    indexer.index_dossier(session, dossier)


def add_claim(
    session: Session,
    dossier: Dossier,
    *,
    text: str,
    stance: str = "neutral",
    confidence: int | None = None,
    origin: str = "user",
    generated_by: str | None = None,
) -> DossierClaim:
    position = int(
        session.execute(
            select(func.coalesce(func.max(DossierClaim.position), -1)).where(
                DossierClaim.dossier_id == dossier.id
            )
        ).scalar_one()
        + 1
    )
    claim = DossierClaim(
        dossier_id=dossier.id,
        text=text,
        stance=stance,
        confidence=confidence,
        position=position,
        origin=origin,
        generated_by=generated_by,
    )
    session.add(claim)
    session.flush()
    return claim


def add_evidence(
    session: Session,
    claim: DossierClaim,
    *,
    excerpt_id: str | None = None,
    source_id: str | None = None,
    stance: str = "supports",
    note: str | None = None,
) -> ClaimEvidence:
    if not excerpt_id and not source_id:
        raise DossierError("evidence needs an excerpt or a source")
    if excerpt_id and session.get(Excerpt, excerpt_id) is None:
        raise DossierError("excerpt does not exist")
    if source_id and session.get(Source, source_id) is None:
        raise DossierError("source does not exist")
    evidence = ClaimEvidence(
        claim_id=claim.id,
        excerpt_id=excerpt_id,
        source_id=source_id,
        stance=stance,
        note=note,
    )
    session.add(evidence)
    session.flush()
    return evidence


def add_event(
    session: Session,
    dossier: Dossier,
    *,
    occurred_on: Any,
    title: str,
    description: str | None = None,
    kind: str = "event",
    source_id: str | None = None,
) -> TimelineEvent:
    if source_id and session.get(Source, source_id) is None:
        raise DossierError("source does not exist")
    event = TimelineEvent(
        dossier_id=dossier.id,
        occurred_on=occurred_on,
        title=title,
        description=description,
        kind=kind,
        source_id=source_id,
    )
    session.add(event)
    session.flush()
    return event
