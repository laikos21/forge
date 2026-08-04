"""Daily review: what changed, what is unfinished, what overlaps.

The "suggested connections" here are **deterministic metadata overlaps** - two
objects that share a tag, an entity or a ticker and are not yet linked. Every
suggestion states the exact overlap it was derived from. Nothing in this module
infers meaning, and the API labels it as ``metadata_overlap`` so the UI can be
honest about what the user is looking at.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..domain import KnowledgeKind, SourceStatus, TargetType
from ..models import (
    Dossier,
    DossierItem,
    Entity,
    EntityMention,
    Excerpt,
    KnowledgeExcerpt,
    KnowledgeObject,
    Link,
    Source,
    Tag,
    Tagging,
)


def _iso(value: dt.datetime | dt.date | None) -> str | None:
    return value.isoformat() if value else None


def recent_imports(session: Session, days: int = 7, limit: int = 20) -> list[dict[str, Any]]:
    since = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    rows = session.execute(
        select(Source).where(Source.imported_at >= since).order_by(Source.imported_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "kind": s.kind,
            "status": s.status,
            "imported_at": _iso(s.imported_at),
            "word_count": s.word_count,
        }
        for s in rows
    ]


def unprocessed_sources(session: Session, limit: int = 25) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Source)
        .where(Source.status.in_([str(SourceStatus.NEEDS_REVIEW), str(SourceStatus.ERROR)]))
        .order_by(Source.imported_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": s.id,
            "title": s.title,
            "kind": s.kind,
            "status": s.status,
            "error_message": s.error_message,
            "warnings": s.extraction_warnings or [],
            "imported_at": _iso(s.imported_at),
        }
        for s in rows
    ]


def open_hypotheses(session: Session, limit: int = 25) -> list[dict[str, Any]]:
    rows = session.execute(
        select(KnowledgeObject)
        .where(KnowledgeObject.kind == str(KnowledgeKind.HYPOTHESIS), KnowledgeObject.status == "open")
        .order_by(KnowledgeObject.created_at)
        .limit(limit)
    ).scalars().all()
    today = dt.datetime.now(dt.UTC)
    return [
        {
            "id": k.id,
            "title": k.title,
            "status": k.status,
            "confidence": k.confidence,
            "age_days": (today - k.created_at).days,
            "evidence_count": len(k.excerpt_links),
            "review_due_on": _iso(k.review_due_on),
        }
        for k in rows
    ]


def recent_dossiers(session: Session, limit: int = 10) -> list[dict[str, Any]]:
    rows = session.execute(
        select(Dossier).order_by(Dossier.updated_at.desc()).limit(limit)
    ).scalars().all()
    return [
        {
            "id": d.id,
            "slug": d.slug,
            "title": d.title,
            "subject_kind": d.subject_kind,
            "status": d.status,
            "updated_at": _iso(d.updated_at),
            "claims": len(d.claims),
            "items": len(d.items),
        }
        for d in rows
    ]


#: Rules and decisions are surfaced this many days before their review date, so
#: the review screen is a queue rather than a list of things already late.
REVIEW_HORIZON_DAYS = 14


def awaiting_review(session: Session, limit: int = 25, horizon_days: int = REVIEW_HORIZON_DAYS) -> list[dict[str, Any]]:
    today = dt.date.today()
    horizon = today + dt.timedelta(days=horizon_days)
    rows = session.execute(
        select(KnowledgeObject)
        .where(
            KnowledgeObject.kind.in_([str(KnowledgeKind.RULE), str(KnowledgeKind.DECISION)]),
            or_(
                KnowledgeObject.review_due_on <= horizon,
                KnowledgeObject.status.in_(["under_review", "proposed"]),
            ),
        )
        .order_by(KnowledgeObject.review_due_on.is_(None), KnowledgeObject.review_due_on)
        .limit(limit)
    ).scalars().all()
    return [
        {
            "id": k.id,
            "kind": k.kind,
            "title": k.title,
            "status": k.status,
            "review_due_on": _iso(k.review_due_on),
            "overdue_days": max((today - k.review_due_on).days, 0) if k.review_due_on else None,
            "due_in_days": (k.review_due_on - today).days if k.review_due_on else None,
        }
        for k in rows
    ]


def _linked_pairs(session: Session) -> set[tuple[str, str, str, str]]:
    pairs: set[tuple[str, str, str, str]] = set()
    for link in session.execute(select(Link)).scalars():
        pairs.add((link.from_type, link.from_id, link.to_type, link.to_id))
        pairs.add((link.to_type, link.to_id, link.from_type, link.from_id))
    for item in session.execute(select(DossierItem)).scalars():
        pairs.add((TargetType.DOSSIER, item.dossier_id, item.target_type, item.target_id))
        pairs.add((item.target_type, item.target_id, TargetType.DOSSIER, item.dossier_id))
    return pairs


def suggested_connections(session: Session, limit: int = 12) -> list[dict[str, Any]]:
    """Objects that share metadata but are not connected yet."""

    linked = _linked_pairs(session)
    suggestions: list[dict[str, Any]] = []

    # 1. A source mentions an entity that a dossier already tracks.
    dossier_entities: dict[str, set[str]] = {}
    entity_names: dict[str, str] = {}
    for dossier in session.execute(select(Dossier)).scalars():
        ids: set[str] = set()
        if dossier.primary_entity_id:
            ids.add(dossier.primary_entity_id)
        for item in dossier.items:
            if item.target_type == TargetType.ENTITY:
                ids.add(item.target_id)
        source_ids = [i.target_id for i in dossier.items if i.target_type == TargetType.SOURCE]
        if source_ids:
            for entity_id in session.execute(
                select(EntityMention.entity_id).where(EntityMention.source_id.in_(source_ids))
            ).scalars():
                ids.add(entity_id)
        if ids:
            dossier_entities[dossier.id] = ids
    for entity in session.execute(select(Entity)).scalars():
        entity_names[entity.id] = f"{entity.kind}:{entity.name}"

    mentions: dict[str, set[str]] = {}
    for mention in session.execute(select(EntityMention)).scalars():
        mentions.setdefault(mention.source_id, set()).add(mention.entity_id)

    sources = {s.id: s for s in session.execute(select(Source)).scalars()}
    dossiers = {d.id: d for d in session.execute(select(Dossier)).scalars()}

    for source_id, entity_ids in mentions.items():
        for dossier_id, dossier_entity_ids in dossier_entities.items():
            shared = entity_ids & dossier_entity_ids
            if not shared:
                continue
            if (TargetType.SOURCE, source_id, TargetType.DOSSIER, dossier_id) in linked:
                continue
            source = sources.get(source_id)
            dossier = dossiers.get(dossier_id)
            if source is None or dossier is None:
                continue
            suggestions.append(
                {
                    "kind": "metadata_overlap",
                    "basis": "shared_entities",
                    "explanation": "Shares "
                    + ", ".join(sorted(entity_names.get(e, e) for e in shared)[:3])
                    + " with this dossier.",
                    "score": len(shared),
                    "from": {"target_type": TargetType.SOURCE.value, "target_id": source_id, "label": source.title},
                    "to": {"target_type": TargetType.DOSSIER.value, "target_id": dossier_id, "label": dossier.title},
                    "suggested_action": "link_source_to_dossier",
                }
            )

    # 2. Objects sharing two or more tags but never linked.
    tag_names = {t.id: t.name for t in session.execute(select(Tag)).scalars()}
    by_target: dict[tuple[str, str], set[str]] = {}
    for tagging in session.execute(select(Tagging)).scalars():
        by_target.setdefault((tagging.target_type, tagging.target_id), set()).add(tagging.tag_id)

    keys = list(by_target)
    for index, left in enumerate(keys):
        for right in keys[index + 1 :]:
            if left[0] == right[0] and left[0] != TargetType.SOURCE:
                continue
            shared = by_target[left] & by_target[right]
            if len(shared) < 2 or (left[0], left[1], right[0], right[1]) in linked:
                continue
            from_ref = _describe(session, *left)
            to_ref = _describe(session, *right)
            if from_ref is None or to_ref is None:
                continue
            suggestions.append(
                {
                    "kind": "metadata_overlap",
                    "basis": "shared_tags",
                    "explanation": "Both tagged "
                    + ", ".join(sorted(tag_names.get(t, t) for t in shared)[:3])
                    + ".",
                    "score": len(shared),
                    "from": from_ref,
                    "to": to_ref,
                    "suggested_action": "create_link",
                }
            )

    suggestions.sort(key=lambda s: -s["score"])
    return suggestions[:limit]


def _describe(session: Session, target_type: str, target_id: str) -> dict[str, Any] | None:
    from . import refs

    info = refs.describe(session, target_type, target_id)
    if not info.exists:
        return None
    return {"target_type": target_type, "target_id": target_id, "label": info.label}


def loose_ends(session: Session) -> dict[str, Any]:
    """Counts of things that are half-finished, for the review header."""

    sources_without_tags = session.execute(
        select(func.count(Source.id)).where(
            ~Source.id.in_(select(Tagging.target_id).where(Tagging.target_type == TargetType.SOURCE))
        )
    ).scalar_one()
    excerpts_without_use = session.execute(
        select(func.count(Excerpt.id)).where(
            ~Excerpt.id.in_(select(KnowledgeExcerpt.excerpt_id)),
            ~Excerpt.id.in_(
                select(DossierItem.target_id).where(DossierItem.target_type == TargetType.EXCERPT)
            ),
        )
    ).scalar_one()
    knowledge_without_evidence = session.execute(
        select(func.count(KnowledgeObject.id)).where(
            ~KnowledgeObject.id.in_(select(KnowledgeExcerpt.knowledge_id)),
            KnowledgeObject.kind.in_([str(KnowledgeKind.INSIGHT), str(KnowledgeKind.HYPOTHESIS)]),
        )
    ).scalar_one()
    return {
        "sources_without_tags": int(sources_without_tags),
        "excerpts_not_used": int(excerpts_without_use),
        "knowledge_without_evidence": int(knowledge_without_evidence),
    }


def dashboard(session: Session, days: int = 7) -> dict[str, Any]:
    return {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "window_days": days,
        "recent_imports": recent_imports(session, days),
        "unprocessed": unprocessed_sources(session),
        "open_hypotheses": open_hypotheses(session),
        "recent_dossiers": recent_dossiers(session),
        "awaiting_review": awaiting_review(session),
        "suggestions": suggested_connections(session),
        "loose_ends": loose_ends(session),
        "disclaimer": (
            "Suggestions are deterministic metadata overlaps (shared tags or entities). "
            "They are not model inferences and carry no judgement about relevance."
        ),
    }


def home_stats(session: Session) -> dict[str, Any]:
    def count(model: Any, *conditions: Any) -> int:
        statement = select(func.count()).select_from(model)
        for condition in conditions:
            statement = statement.where(condition)
        return int(session.execute(statement).scalar_one())

    kinds = session.execute(
        select(Source.kind, func.count(Source.id)).group_by(Source.kind).order_by(func.count(Source.id).desc())
    ).all()
    knowledge_kinds = session.execute(
        select(KnowledgeObject.kind, func.count(KnowledgeObject.id)).group_by(KnowledgeObject.kind)
    ).all()
    return {
        "sources": count(Source),
        "sources_by_kind": {row[0]: int(row[1]) for row in kinds},
        "needs_review": count(Source, Source.status == str(SourceStatus.NEEDS_REVIEW)),
        "errors": count(Source, Source.status == str(SourceStatus.ERROR)),
        "excerpts": count(Excerpt),
        "knowledge": count(KnowledgeObject),
        "knowledge_by_kind": {row[0]: int(row[1]) for row in knowledge_kinds},
        "dossiers": count(Dossier),
        "entities": count(Entity),
        "tags": count(Tag),
        "links": count(Link),
        "words_indexed": int(session.execute(select(func.coalesce(func.sum(Source.word_count), 0))).scalar_one()),
    }
