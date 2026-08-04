"""Entities, tags, links and collections - the connective tissue."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import RELATION_INVERSES, TargetType
from ..lib.text import slugify
from ..models import (
    Collection,
    CollectionItem,
    Entity,
    EntityMention,
    Source,
    Tag,
    Tagging,
)
from ..schemas import (
    CollectionCreate,
    CollectionItemCreate,
    EntityCreate,
    EntityOut,
    EntityUpdate,
    LinkCreate,
    TagCreate,
    TagOut,
)
from ..services import entities as entity_service
from ..services import indexer, links, refs, tagging
from .serializers import entity_out, source_summaries

entities_router = APIRouter(prefix="/api/entities", tags=["entities"])
tags_router = APIRouter(prefix="/api/tags", tags=["tags"])
links_router = APIRouter(prefix="/api/links", tags=["links"])
collections_router = APIRouter(prefix="/api/collections", tags=["collections"])


# --- entities --------------------------------------------------------------


@entities_router.get("")
def list_entities(
    session: Annotated[Session, Depends(get_db)],
    kind: Annotated[list[str] | None, Query()] = None,
    q: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict:
    statement = select(Entity)
    if kind:
        statement = statement.where(Entity.kind.in_(kind))
    if q:
        statement = statement.where(Entity.name.ilike(f"%{q.strip()}%"))
    rows = session.execute(statement.order_by(Entity.kind, Entity.name).limit(limit)).scalars().all()
    counts = entity_service.source_counts_by_entity(session)
    facets = session.execute(select(Entity.kind, func.count(Entity.id)).group_by(Entity.kind)).all()
    return {
        "items": [entity_out(e, counts.get(e.id, 0)).model_dump() for e in rows],
        "total": len(rows),
        "facets": {"kind": {row[0]: int(row[1]) for row in facets}},
    }


@entities_router.post("", response_model=EntityOut, status_code=201)
def create_entity(payload: EntityCreate, session: Annotated[Session, Depends(get_db)]) -> EntityOut:
    try:
        entity = entity_service.get_or_create_entity(
            session,
            payload.kind.value,
            payload.name,
            description=payload.description,
            data=payload.data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if payload.aliases:
        entity.aliases = payload.aliases
    session.flush()
    indexer.index_entity(session, entity)
    return entity_out(entity)


@entities_router.get("/{entity_id}")
def entity_detail(entity_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    sources = session.execute(
        select(Source)
        .join(EntityMention, EntityMention.source_id == Source.id)
        .where(EntityMention.entity_id == entity_id)
        .order_by(Source.imported_at.desc())
    ).scalars().all()
    return {
        "entity": entity_out(entity, len(sources)).model_dump(),
        "sources": [s.model_dump() for s in source_summaries(session, sources)],
        "links": [n.as_dict() for n in links.neighbours(session, TargetType.ENTITY, entity_id)],
    }


@entities_router.patch("/{entity_id}", response_model=EntityOut)
def update_entity(
    entity_id: str,
    payload: EntityUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> EntityOut:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        entity.name = data["name"]
        entity.normalized_name = entity_service.normalize_name(data["name"])
    for field in ("description", "aliases", "data"):
        if field in data and data[field] is not None:
            setattr(entity, field, data[field])
    session.flush()
    indexer.index_entity(session, entity)
    return entity_out(entity)


@entities_router.delete("/{entity_id}")
def delete_entity(entity_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    indexer.remove(session, TargetType.ENTITY, entity_id)
    links.delete_links_for(session, TargetType.ENTITY, entity_id)
    tagging.delete_taggings_for(session, TargetType.ENTITY, entity_id)
    session.delete(entity)
    return {"deleted": entity_id}


@entities_router.post("/{entity_id}/mentions/{source_id}")
def link_entity_to_source(
    entity_id: str,
    source_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    entity = session.get(Entity, entity_id)
    source = session.get(Source, source_id)
    if entity is None or source is None:
        raise HTTPException(status_code=404, detail="Entity or source not found")
    entity_service.attach_entities(
        session, source, [{"kind": entity.kind, "name": entity.name, "detector": "user"}]
    )
    return {"entity_id": entity_id, "source_id": source_id, "confirmed": True}


@entities_router.delete("/{entity_id}/mentions/{source_id}")
def unlink_entity_from_source(
    entity_id: str,
    source_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    mention = session.execute(
        select(EntityMention).where(
            EntityMention.entity_id == entity_id, EntityMention.source_id == source_id
        )
    ).scalar_one_or_none()
    if mention is None:
        raise HTTPException(status_code=404, detail="Mention not found")
    session.delete(mention)
    return {"deleted": True}


# --- tags ------------------------------------------------------------------


@tags_router.get("")
def list_tags(session: Annotated[Session, Depends(get_db)]) -> dict:
    counts = tagging.usage_counts(session)
    rows = session.execute(select(Tag).order_by(Tag.name)).scalars().all()
    return {
        "items": [
            TagOut.model_validate(tag).model_copy(update={"usage_count": counts.get(tag.id, 0)}).model_dump()
            for tag in rows
        ],
        "total": len(rows),
    }


@tags_router.post("", response_model=TagOut, status_code=201)
def create_tag(payload: TagCreate, session: Annotated[Session, Depends(get_db)]) -> TagOut:
    tag = tagging.get_or_create_tag(session, payload.name, color=payload.color)
    if payload.description:
        tag.description = payload.description
    session.flush()
    return TagOut.model_validate(tag)


@tags_router.patch("/{tag_id}", response_model=TagOut)
def update_tag(tag_id: str, payload: TagCreate, session: Annotated[Session, Depends(get_db)]) -> TagOut:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    tag.name = payload.name
    tag.slug = slugify(payload.name)
    tag.color = payload.color
    tag.description = payload.description
    session.flush()
    return TagOut.model_validate(tag)


@tags_router.delete("/{tag_id}")
def delete_tag(tag_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    tag = session.get(Tag, tag_id)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    removed = session.execute(select(Tagging).where(Tagging.tag_id == tag_id)).scalars().all()
    for tagging_row in removed:
        session.delete(tagging_row)
    session.delete(tag)
    return {"deleted": tag_id, "taggings_removed": len(removed)}


@tags_router.get("/{tag_slug}/targets")
def tag_targets(tag_slug: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    tag = session.execute(select(Tag).where(Tag.slug == tag_slug)).scalar_one_or_none()
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    rows = session.execute(select(Tagging).where(Tagging.tag_id == tag.id)).scalars().all()
    return {
        "tag": TagOut.model_validate(tag).model_dump(),
        "items": [refs.describe(session, r.target_type, r.target_id).as_dict() for r in rows],
    }


# --- links -----------------------------------------------------------------


@links_router.get("")
def get_links(
    session: Annotated[Session, Depends(get_db)],
    target_type: str,
    target_id: str,
) -> dict:
    try:
        TargetType(target_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown target type {target_type!r}") from exc
    return {
        "items": [n.as_dict() for n in links.neighbours(session, target_type, target_id)],
        "relations": sorted(RELATION_INVERSES),
    }


@links_router.post("", status_code=201)
def create_link(payload: LinkCreate, session: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        link = links.create_link(
            session,
            from_type=payload.from_type.value,
            from_id=payload.from_id,
            to_type=payload.to_type.value,
            to_id=payload.to_id,
            relation=payload.relation,
            note=payload.note,
        )
    except links.LinkError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": link.id,
        "from": refs.describe(session, link.from_type, link.from_id).as_dict(),
        "to": refs.describe(session, link.to_type, link.to_id).as_dict(),
        "relation": link.relation,
    }


@links_router.delete("/{link_id}")
def delete_link(link_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    if not links.delete_link(session, link_id):
        raise HTTPException(status_code=404, detail="Link not found")
    return {"deleted": link_id}


# --- collections -----------------------------------------------------------


@collections_router.get("")
def list_collections(session: Annotated[Session, Depends(get_db)]) -> dict:
    rows = session.execute(select(Collection).order_by(Collection.name)).scalars().all()
    return {
        "items": [
            {
                "id": c.id,
                "slug": c.slug,
                "name": c.name,
                "description": c.description,
                "item_count": len(c.items),
                "updated_at": c.updated_at.isoformat(),
            }
            for c in rows
        ],
        "total": len(rows),
    }


@collections_router.post("", status_code=201)
def create_collection(payload: CollectionCreate, session: Annotated[Session, Depends(get_db)]) -> dict:
    slug = slugify(payload.name)
    if session.execute(select(Collection).where(Collection.slug == slug)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="A collection with that name already exists.")
    collection = Collection(slug=slug, name=payload.name, description=payload.description)
    session.add(collection)
    session.flush()
    return {"id": collection.id, "slug": collection.slug, "name": collection.name}


@collections_router.get("/{collection_id}")
def collection_detail(collection_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {
        "id": collection.id,
        "slug": collection.slug,
        "name": collection.name,
        "description": collection.description,
        "items": [
            {"id": item.id, "note": item.note, **refs.describe(session, item.target_type, item.target_id).as_dict()}
            for item in collection.items
        ],
    }


@collections_router.post("/{collection_id}/items", status_code=201)
def add_collection_item(
    collection_id: str,
    payload: CollectionItemCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if not refs.exists(session, payload.target_type.value, payload.target_id):
        raise HTTPException(status_code=422, detail="Target object does not exist")
    existing = session.execute(
        select(CollectionItem).where(
            CollectionItem.collection_id == collection_id,
            CollectionItem.target_type == payload.target_type.value,
            CollectionItem.target_id == payload.target_id,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return {"id": existing.id, "already_present": True}
    item = CollectionItem(
        collection_id=collection_id,
        target_type=payload.target_type.value,
        target_id=payload.target_id,
        position=len(collection.items),
        note=payload.note,
    )
    session.add(item)
    session.flush()
    return {"id": item.id, "already_present": False}


@collections_router.delete("/{collection_id}/items/{item_id}")
def remove_collection_item(
    collection_id: str,
    item_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    item = session.get(CollectionItem, item_id)
    if item is None or item.collection_id != collection_id:
        raise HTTPException(status_code=404, detail="Collection item not found")
    session.delete(item)
    return {"deleted": item_id}


@collections_router.delete("/{collection_id}")
def delete_collection(collection_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    session.delete(collection)
    return {"deleted": collection_id}
