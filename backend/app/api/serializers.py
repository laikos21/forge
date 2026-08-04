"""ORM -> API payload conversion shared by the routers."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain import TargetType
from ..lib.provenance import locator_label, provenance_dict
from ..models import (
    Dossier,
    DossierClaim,
    DossierItem,
    Entity,
    Excerpt,
    KnowledgeExcerpt,
    KnowledgeObject,
    Source,
    Tag,
)
from ..schemas import (
    DocumentOut,
    DossierSummary,
    EntityOut,
    ExcerptOut,
    KnowledgeOut,
    SourceSummary,
    TagSummary,
)
from ..services import storage, tagging


def tag_summaries(tags: list[Tag]) -> list[TagSummary]:
    return [TagSummary.model_validate(tag) for tag in tags]


def source_summary(session: Session, source: Source, *, tags: list[Tag] | None = None) -> SourceSummary:
    payload = SourceSummary.model_validate(source)
    payload.tags = tag_summaries(tags if tags is not None else tagging.tags_for(session, TargetType.SOURCE, source.id))
    payload.excerpt_count = int(
        session.execute(select(func.count(Excerpt.id)).where(Excerpt.source_id == source.id)).scalar_one()
    )
    payload.has_original = storage.blob_exists(source.storage_path)
    return payload


def source_summaries(session: Session, sources: list[Source]) -> list[SourceSummary]:
    ids = [s.id for s in sources]
    tags = tagging.tags_for_many(session, TargetType.SOURCE, ids)
    counts = {
        row[0]: int(row[1])
        for row in session.execute(
            select(Excerpt.source_id, func.count(Excerpt.id))
            .where(Excerpt.source_id.in_(ids))
            .group_by(Excerpt.source_id)
        ).all()
    } if ids else {}
    out: list[SourceSummary] = []
    for source in sources:
        payload = SourceSummary.model_validate(source)
        payload.tags = tag_summaries(tags.get(source.id, []))
        payload.excerpt_count = counts.get(source.id, 0)
        payload.has_original = storage.blob_exists(source.storage_path)
        out.append(payload)
    return out


def document_out(document: Any) -> DocumentOut:
    payload = DocumentOut.model_validate(document)
    payload.locator_label = locator_label(document.locator)
    return payload


def excerpt_out(session: Session, excerpt: Excerpt, *, source: Source | None = None) -> ExcerptOut:
    source = source or session.get(Source, excerpt.source_id)
    payload = ExcerptOut.model_validate(excerpt)
    if source is not None:
        payload.provenance = provenance_dict(
            source_id=source.id,
            source_title=source.title,
            kind=source.kind,
            locator=excerpt.locator,
            char_start=excerpt.char_start,
            char_end=excerpt.char_end,
            author=source.author,
            published_on=source.published_on.isoformat() if source.published_on else None,
            url=source.source_url,
            method=source.extraction_method,
            created_at=excerpt.created_at.isoformat(),
        )
    used_by: list[dict[str, Any]] = []
    for link in excerpt.knowledge_links:
        knowledge = link.knowledge
        used_by.append(
            {
                "target_type": TargetType.KNOWLEDGE.value,
                "target_id": knowledge.id,
                "label": knowledge.title,
                "kind": knowledge.kind,
                "stance": link.stance,
            }
        )
    for item in session.execute(
        select(DossierItem).where(
            DossierItem.target_type == TargetType.EXCERPT, DossierItem.target_id == excerpt.id
        )
    ).scalars():
        dossier = session.get(Dossier, item.dossier_id)
        if dossier is not None:
            used_by.append(
                {
                    "target_type": TargetType.DOSSIER.value,
                    "target_id": dossier.id,
                    "label": dossier.title,
                    "kind": dossier.subject_kind,
                    "stance": item.section,
                }
            )
    payload.used_by = used_by
    return payload


def knowledge_out(session: Session, obj: KnowledgeObject, *, tags: list[Tag] | None = None) -> KnowledgeOut:
    payload = KnowledgeOut.model_validate(obj)
    payload.tags = tag_summaries(
        tags if tags is not None else tagging.tags_for(session, TargetType.KNOWLEDGE, obj.id)
    )
    evidence: list[dict[str, Any]] = []
    for link in obj.excerpt_links:
        excerpt = link.excerpt
        source = session.get(Source, excerpt.source_id) if excerpt else None
        evidence.append(
            {
                "id": link.id,
                "stance": link.stance,
                "note": link.note,
                "excerpt_id": link.excerpt_id,
                "text": excerpt.text if excerpt else "",
                "locator": excerpt.locator if excerpt else {},
                "locator_label": locator_label(excerpt.locator) if excerpt else "",
                "source_id": source.id if source else None,
                "source_title": source.title if source else "(deleted source)",
                "source_kind": source.kind if source else None,
            }
        )
    payload.evidence = evidence
    return payload


def knowledge_list(session: Session, objects: list[KnowledgeObject]) -> list[KnowledgeOut]:
    ids = [o.id for o in objects]
    tags = tagging.tags_for_many(session, TargetType.KNOWLEDGE, ids)
    return [knowledge_out(session, obj, tags=tags.get(obj.id, [])) for obj in objects]


def entity_out(entity: Entity, source_count: int = 0) -> EntityOut:
    payload = EntityOut.model_validate(entity)
    payload.source_count = source_count
    return payload


def dossier_summary(session: Session, dossier: Dossier, *, tags: list[Tag] | None = None) -> DossierSummary:
    payload = DossierSummary.model_validate(dossier)
    payload.tags = tag_summaries(
        tags if tags is not None else tagging.tags_for(session, TargetType.DOSSIER, dossier.id)
    )
    payload.counts = {
        "items": len(dossier.items),
        "claims": len(dossier.claims),
        "timeline": len(dossier.events),
        "sources": sum(1 for i in dossier.items if i.target_type == TargetType.SOURCE),
    }
    return payload


def claim_out(session: Session, claim: DossierClaim) -> dict[str, Any]:
    return {
        "id": claim.id,
        "dossier_id": claim.dossier_id,
        "text": claim.text,
        "stance": claim.stance,
        "confidence": claim.confidence,
        "status": claim.status,
        "position": claim.position,
        "origin": claim.origin,
        "generated_by": claim.generated_by,
        "evidence": [
            {
                "id": item.id,
                "stance": item.stance,
                "note": item.note,
                "excerpt_id": item.excerpt_id,
                "source_id": item.source_id,
            }
            for item in claim.evidence
        ],
    }


def evidence_count(session: Session, knowledge_id: str) -> int:
    return int(
        session.execute(
            select(func.count(KnowledgeExcerpt.id)).where(KnowledgeExcerpt.knowledge_id == knowledge_id)
        ).scalar_one()
    )
