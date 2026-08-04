"""Knowledge objects: insights, rules, hypotheses, decisions, quotes, notes."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import KNOWLEDGE_STATUSES, TargetType
from ..models import Dossier, Excerpt, KnowledgeExcerpt, KnowledgeObject, Source
from ..schemas import (
    EvidenceCreate,
    KnowledgeCreate,
    KnowledgeOut,
    KnowledgeUpdate,
    PromoteExcerpt,
    TagsPut,
)
from ..services import dossiers as dossier_service
from ..services import indexer, links, tagging
from ..services.llm import operations as llm_operations
from .serializers import knowledge_list, knowledge_out

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _attach_excerpts(session: Session, obj: KnowledgeObject, excerpt_ids: list[str], stance: str = "supports") -> None:
    for excerpt_id in excerpt_ids:
        excerpt = session.get(Excerpt, excerpt_id)
        if excerpt is None:
            raise HTTPException(status_code=400, detail=f"excerpt {excerpt_id} does not exist")
        exists = session.execute(
            select(KnowledgeExcerpt).where(
                KnowledgeExcerpt.knowledge_id == obj.id, KnowledgeExcerpt.excerpt_id == excerpt_id
            )
        ).scalar_one_or_none()
        if exists is None:
            session.add(KnowledgeExcerpt(knowledge_id=obj.id, excerpt_id=excerpt_id, stance=stance))
    session.flush()


@router.get("")
def list_knowledge(
    session: Annotated[Session, Depends(get_db)],
    kind: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    q: str | None = None,
    origin: str | None = None,
    has_evidence: bool | None = None,
    sort: str = "updated_desc",
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(KnowledgeObject)
    if kind:
        statement = statement.where(KnowledgeObject.kind.in_(kind))
    if status:
        statement = statement.where(KnowledgeObject.status.in_(status))
    if origin:
        statement = statement.where(KnowledgeObject.origin == origin)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(KnowledgeObject.title.ilike(pattern), KnowledgeObject.body.ilike(pattern))
        )
    if tag:
        matching = tagging.targets_with_tags(session, TargetType.KNOWLEDGE, tag)
        statement = statement.where(KnowledgeObject.id.in_(matching or ["__none__"]))
    if has_evidence is not None:
        subquery = select(KnowledgeExcerpt.knowledge_id)
        statement = statement.where(
            KnowledgeObject.id.in_(subquery) if has_evidence else ~KnowledgeObject.id.in_(subquery)
        )

    total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    order = {
        "updated_desc": KnowledgeObject.updated_at.desc(),
        "created_desc": KnowledgeObject.created_at.desc(),
        "title_asc": KnowledgeObject.title.asc(),
        "confidence_desc": KnowledgeObject.confidence.desc(),
    }.get(sort, KnowledgeObject.updated_at.desc())
    rows = session.execute(statement.order_by(order).offset(offset).limit(limit)).scalars().all()

    counts = session.execute(
        select(KnowledgeObject.kind, func.count(KnowledgeObject.id)).group_by(KnowledgeObject.kind)
    ).all()
    return {
        "items": [k.model_dump() for k in knowledge_list(session, rows)],
        "total": total,
        "facets": {"kind": {row[0]: int(row[1]) for row in counts}},
        "statuses": KNOWLEDGE_STATUSES,
    }


@router.post("", response_model=KnowledgeOut, status_code=201)
def create_knowledge(payload: KnowledgeCreate, session: Annotated[Session, Depends(get_db)]) -> KnowledgeOut:
    obj = KnowledgeObject(
        kind=payload.kind.value,
        title=payload.title,
        body=payload.body,
        status=payload.status or KNOWLEDGE_STATUSES[payload.kind][0],
        confidence=payload.confidence,
        review_due_on=payload.review_due_on,
        outcome=payload.outcome,
        data=payload.data,
        origin=payload.origin,
        generated_by=payload.generated_by,
        generation_id=payload.generation_id,
    )
    session.add(obj)
    session.flush()
    if payload.excerpt_ids:
        _attach_excerpts(session, obj, payload.excerpt_ids)
    if payload.tags:
        tagging.set_tags(session, TargetType.KNOWLEDGE, obj.id, payload.tags)
    if payload.generation_id:
        llm_operations.accept_generation(session, payload.generation_id)
    indexer.index_knowledge(session, obj)
    return knowledge_out(session, obj)


@router.get("/{knowledge_id}", response_model=KnowledgeOut)
def get_knowledge(knowledge_id: str, session: Annotated[Session, Depends(get_db)]) -> KnowledgeOut:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    return knowledge_out(session, obj)


@router.get("/{knowledge_id}/detail")
def knowledge_detail(knowledge_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    return {
        "knowledge": knowledge_out(session, obj).model_dump(),
        "links": [n.as_dict() for n in links.neighbours(session, TargetType.KNOWLEDGE, obj.id)],
        "allowed_statuses": KNOWLEDGE_STATUSES[obj.kind],
    }


@router.patch("/{knowledge_id}", response_model=KnowledgeOut)
def update_knowledge(
    knowledge_id: str,
    payload: KnowledgeUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeOut:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    data = payload.model_dump(exclude_unset=True)

    if "status" in data and data["status"] is not None:
        allowed = KNOWLEDGE_STATUSES[obj.kind]
        if data["status"] not in allowed:
            raise HTTPException(status_code=422, detail=f"status must be one of {allowed}")
    resolved = data.pop("resolved", None)
    for field, value in data.items():
        setattr(obj, field, value)
    if resolved is True:
        obj.resolved_at = dt.datetime.now(dt.UTC)
    elif resolved is False:
        obj.resolved_at = None
    session.flush()
    indexer.index_knowledge(session, obj)
    return knowledge_out(session, obj)


@router.delete("/{knowledge_id}")
def delete_knowledge(knowledge_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    indexer.remove(session, TargetType.KNOWLEDGE, knowledge_id)
    tagging.delete_taggings_for(session, TargetType.KNOWLEDGE, knowledge_id)
    links.delete_links_for(session, TargetType.KNOWLEDGE, knowledge_id)
    session.delete(obj)
    return {"deleted": knowledge_id}


@router.post("/{knowledge_id}/evidence", response_model=KnowledgeOut, status_code=201)
def add_evidence(
    knowledge_id: str,
    payload: EvidenceCreate,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeOut:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    excerpt = session.get(Excerpt, payload.excerpt_id)
    if excerpt is None:
        raise HTTPException(status_code=400, detail="Excerpt does not exist")
    existing = session.execute(
        select(KnowledgeExcerpt).where(
            KnowledgeExcerpt.knowledge_id == knowledge_id,
            KnowledgeExcerpt.excerpt_id == payload.excerpt_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            KnowledgeExcerpt(
                knowledge_id=knowledge_id,
                excerpt_id=payload.excerpt_id,
                stance=payload.stance.value,
                note=payload.note,
            )
        )
    else:
        existing.stance = payload.stance.value
        existing.note = payload.note
    session.flush()
    session.refresh(obj)
    return knowledge_out(session, obj)


@router.delete("/{knowledge_id}/evidence/{link_id}")
def remove_evidence(
    knowledge_id: str,
    link_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    link = session.get(KnowledgeExcerpt, link_id)
    if link is None or link.knowledge_id != knowledge_id:
        raise HTTPException(status_code=404, detail="Evidence link not found")
    session.delete(link)
    return {"deleted": link_id}


@router.put("/{knowledge_id}/tags")
def set_knowledge_tags(
    knowledge_id: str,
    payload: TagsPut,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    tags = tagging.set_tags(session, TargetType.KNOWLEDGE, knowledge_id, payload.tags)
    return {"tags": [{"id": t.id, "slug": t.slug, "name": t.name, "color": t.color} for t in tags]}


promote_router = APIRouter(prefix="/api/excerpts", tags=["knowledge"])


@promote_router.post("/{excerpt_id}/promote", response_model=KnowledgeOut, status_code=201)
def promote_excerpt(
    excerpt_id: str,
    payload: PromoteExcerpt,
    session: Annotated[Session, Depends(get_db)],
) -> KnowledgeOut:
    """Turn an excerpt into an insight / rule / hypothesis / decision, keeping it
    attached as the first piece of evidence."""

    excerpt = session.get(Excerpt, excerpt_id)
    if excerpt is None:
        raise HTTPException(status_code=404, detail="Excerpt not found")
    source = session.get(Source, excerpt.source_id)

    obj = KnowledgeObject(
        kind=payload.kind.value,
        title=payload.title,
        body=payload.body or excerpt.text,
        status=KNOWLEDGE_STATUSES[payload.kind][0],
        confidence=payload.confidence,
        origin="user",
    )
    session.add(obj)
    session.flush()
    session.add(
        KnowledgeExcerpt(
            knowledge_id=obj.id,
            excerpt_id=excerpt.id,
            stance=payload.stance.value,
            note=f"Promoted from {source.title}" if source else None,
        )
    )
    if payload.tags:
        tagging.set_tags(session, TargetType.KNOWLEDGE, obj.id, payload.tags)
    if source is not None:
        links.create_link(
            session,
            from_type=TargetType.KNOWLEDGE,
            from_id=obj.id,
            to_type=TargetType.SOURCE,
            to_id=source.id,
            relation="derived_from",
        )
    if payload.dossier_id:
        dossier = session.get(Dossier, payload.dossier_id)
        if dossier is None:
            raise HTTPException(status_code=400, detail="Dossier does not exist")
        dossier_service.add_item(session, dossier, TargetType.KNOWLEDGE, obj.id, section="knowledge")

    session.flush()
    indexer.index_knowledge(session, obj)
    session.refresh(obj)
    return knowledge_out(session, obj)
