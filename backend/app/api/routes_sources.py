"""Library: sources, extracted documents, original files and excerpts."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import TargetType
from ..lib.provenance import locator_label
from ..models import Document, EntityMention, Excerpt, Source
from ..schemas import (
    ExcerptCreate,
    ExcerptOut,
    ExcerptUpdate,
    SourceSummary,
    SourceUpdate,
    TagsPut,
)
from ..services import indexer, links, storage, tagging
from .serializers import document_out, excerpt_out, source_summaries, source_summary

router = APIRouter(prefix="/api", tags=["library"])

SORTS: dict[str, Any] = {
    "imported_desc": Source.imported_at.desc(),
    "imported_asc": Source.imported_at.asc(),
    "updated_desc": Source.updated_at.desc(),
    "title_asc": Source.title.asc(),
    "title_desc": Source.title.desc(),
    "words_desc": Source.word_count.desc(),
    "published_desc": Source.published_on.desc(),
}


@router.get("/sources")
def list_sources(
    session: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    kind: Annotated[list[str] | None, Query()] = None,
    status: Annotated[list[str] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
    entity_id: Annotated[list[str] | None, Query()] = None,
    author: str | None = None,
    language: str | None = None,
    date_field: str = "imported",
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    include_demo: bool = True,
    sort: str = "imported_desc",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=200),
) -> dict:
    statement = select(Source)

    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(
            or_(Source.title.ilike(pattern), Source.author.ilike(pattern), Source.summary.ilike(pattern))
        )
    if kind:
        statement = statement.where(Source.kind.in_(kind))
    if status:
        statement = statement.where(Source.status.in_(status))
    if author:
        statement = statement.where(Source.author.ilike(f"%{author.strip()}%"))
    if language:
        statement = statement.where(Source.language == language)
    if not include_demo:
        statement = statement.where(Source.is_demo.is_(False))
    if entity_id:
        statement = statement.where(
            Source.id.in_(select(EntityMention.source_id).where(EntityMention.entity_id.in_(entity_id)))
        )
    if tag:
        matching = tagging.targets_with_tags(session, TargetType.SOURCE, tag)
        statement = statement.where(Source.id.in_(matching or ["__none__"]))

    column = Source.published_on if date_field == "published" else Source.imported_at
    if date_from:
        value = date_from if date_field == "published" else dt.datetime.combine(date_from, dt.time.min, dt.UTC)
        statement = statement.where(column >= value)
    if date_to:
        value = date_to if date_field == "published" else dt.datetime.combine(date_to, dt.time.max, dt.UTC)
        statement = statement.where(column <= value)

    total = int(
        session.execute(select(func.count()).select_from(statement.subquery())).scalar_one()
    )
    statement = statement.order_by(SORTS.get(sort, SORTS["imported_desc"]))
    rows = session.execute(statement.offset((page - 1) * page_size).limit(page_size)).scalars().all()

    facet_rows = session.execute(select(Source.kind, func.count(Source.id)).group_by(Source.kind)).all()
    status_rows = session.execute(select(Source.status, func.count(Source.id)).group_by(Source.status)).all()

    return {
        "items": [s.model_dump() for s in source_summaries(session, rows)],
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-total // page_size)),
        "facets": {
            "kind": {row[0]: int(row[1]) for row in facet_rows},
            "status": {row[0]: int(row[1]) for row in status_rows},
        },
    }


@router.get("/sources/{source_id}", response_model=SourceSummary)
def get_source(source_id: str, session: Annotated[Session, Depends(get_db)]) -> SourceSummary:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source_summary(session, source)


@router.get("/sources/{source_id}/detail")
def source_detail(source_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    entities = session.execute(
        select(EntityMention).where(EntityMention.source_id == source.id)
    ).scalars().all()
    excerpts = session.execute(
        select(Excerpt).where(Excerpt.source_id == source.id).order_by(Excerpt.char_start)
    ).scalars().all()
    return {
        "source": source_summary(session, source).model_dump(),
        "detected_metadata": source.detected_metadata or {},
        "warnings": source.extraction_warnings or [],
        "documents": [document_out(d).model_dump() for d in source.documents],
        "excerpts": [excerpt_out(session, e, source=source).model_dump() for e in excerpts],
        "entities": [
            {
                "id": mention.entity.id,
                "kind": mention.entity.kind,
                "name": mention.entity.name,
                "count": mention.count,
                "confirmed": mention.confirmed,
                "detector": mention.detector,
            }
            for mention in entities
        ],
        "links": [n.as_dict() for n in links.neighbours(session, TargetType.SOURCE, source.id)],
    }


@router.get("/sources/{source_id}/text")
def source_text(
    source_id: str,
    session: Annotated[Session, Depends(get_db)],
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=40000, ge=1000, le=200000),
) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    chunk = source.text[offset : offset + limit]
    return {
        "source_id": source.id,
        "offset": offset,
        "limit": limit,
        "char_count": source.char_count,
        "text": chunk,
        "has_more": offset + limit < source.char_count,
    }


@router.get("/sources/{source_id}/documents")
def source_documents(source_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return {
        "items": [document_out(d).model_dump() for d in source.documents],
        "total": len(source.documents),
    }


@router.get("/sources/{source_id}/file")
def source_file(source_id: str, session: Annotated[Session, Depends(get_db)], download: bool = False) -> Response:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if not source.storage_path or not storage.blob_exists(source.storage_path):
        raise HTTPException(status_code=404, detail="Original file is not available for this source.")
    path = storage.blob_path(source.storage_path)
    filename = source.original_filename or f"{source.id}{path.suffix}"
    disposition = "attachment" if download else "inline"

    def stream() -> Any:
        with path.open("rb") as handle:
            while chunk := handle.read(64 * 1024):
                yield chunk

    return StreamingResponse(
        stream(),
        media_type=source.mime_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Content-Length": str(path.stat().st_size),
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.patch("/sources/{source_id}", response_model=SourceSummary)
def update_source(
    source_id: str,
    payload: SourceUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> SourceSummary:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(source, field, value)
    session.flush()
    indexer.index_source(session, source)
    return source_summary(session, source)


@router.delete("/sources/{source_id}")
def delete_source(source_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    excerpt_ids = [e.id for e in source.excerpts]
    storage_path, content_hash = source.storage_path, source.content_hash

    for excerpt_id in excerpt_ids:
        indexer.remove(session, TargetType.EXCERPT, excerpt_id)
        tagging.delete_taggings_for(session, TargetType.EXCERPT, excerpt_id)
        links.delete_links_for(session, TargetType.EXCERPT, excerpt_id)
    indexer.remove(session, TargetType.SOURCE, source.id)
    tagging.delete_taggings_for(session, TargetType.SOURCE, source.id)
    links.delete_links_for(session, TargetType.SOURCE, source.id)

    session.delete(source)
    session.flush()

    still_used = session.execute(
        select(func.count(Source.id)).where(Source.content_hash == content_hash)
    ).scalar_one()
    removed_blob = False
    if storage_path:
        removed_blob = storage.delete_blob_if_orphan(storage_path, bool(still_used))

    return {"deleted": source_id, "excerpts_deleted": len(excerpt_ids), "original_removed": removed_blob}


@router.put("/sources/{source_id}/tags")
def set_source_tags(
    source_id: str,
    payload: TagsPut,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    tags = tagging.set_tags(session, TargetType.SOURCE, source_id, payload.tags)
    return {"tags": [{"id": t.id, "slug": t.slug, "name": t.name, "color": t.color} for t in tags]}


# --- excerpts --------------------------------------------------------------


@router.get("/sources/{source_id}/excerpts")
def list_source_excerpts(source_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    rows = session.execute(
        select(Excerpt).where(Excerpt.source_id == source_id).order_by(Excerpt.char_start)
    ).scalars().all()
    return {"items": [excerpt_out(session, e, source=source).model_dump() for e in rows], "total": len(rows)}


@router.post("/sources/{source_id}/excerpts", response_model=ExcerptOut, status_code=201)
def create_excerpt(
    source_id: str,
    payload: ExcerptCreate,
    session: Annotated[Session, Depends(get_db)],
) -> ExcerptOut:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    document = None
    if payload.document_id:
        document = session.get(Document, payload.document_id)
        if document is None or document.source_id != source_id:
            raise HTTPException(status_code=400, detail="document_id does not belong to this source")

    char_start, char_end = payload.char_start, payload.char_end
    if char_start is None or char_end is None:
        found = source.text.find(payload.text.strip()[:200])
        if found >= 0:
            char_start, char_end = found, found + len(payload.text.strip())
    if char_start is not None and char_end is not None and char_end > source.char_count:
        raise HTTPException(status_code=400, detail="excerpt range is outside the source text")

    if document is None and char_start is not None:
        document = next(
            (d for d in source.documents if d.char_start <= char_start < max(d.char_end, d.char_start + 1)),
            None,
        )

    locator = dict(payload.locator or {})
    if document is not None:
        locator = {**document.locator, **locator}
    if char_start is not None:
        locator.setdefault("char_start", char_start)

    excerpt = Excerpt(
        source_id=source_id,
        document_id=document.id if document else None,
        text=payload.text.strip(),
        note=payload.note,
        char_start=char_start,
        char_end=char_end,
        locator=locator,
        origin="user",
        created_via="manual_selection",
    )
    session.add(excerpt)
    session.flush()
    indexer.index_excerpt(session, excerpt)
    return excerpt_out(session, excerpt, source=source)


@router.get("/excerpts")
def list_excerpts(
    session: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    unused_only: bool = False,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(Excerpt)
    if q:
        statement = statement.where(Excerpt.text.ilike(f"%{q.strip()}%"))
    if unused_only:
        from ..models import DossierItem, KnowledgeExcerpt

        statement = statement.where(
            ~Excerpt.id.in_(select(KnowledgeExcerpt.excerpt_id)),
            ~Excerpt.id.in_(
                select(DossierItem.target_id).where(DossierItem.target_type == TargetType.EXCERPT)
            ),
        )
    total = int(session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
    rows = session.execute(
        statement.order_by(Excerpt.created_at.desc()).offset(offset).limit(limit)
    ).scalars().all()
    return {
        "items": [excerpt_out(session, e).model_dump() for e in rows],
        "total": total,
    }


@router.get("/excerpts/{excerpt_id}", response_model=ExcerptOut)
def get_excerpt(excerpt_id: str, session: Annotated[Session, Depends(get_db)]) -> ExcerptOut:
    excerpt = session.get(Excerpt, excerpt_id)
    if excerpt is None:
        raise HTTPException(status_code=404, detail="Excerpt not found")
    return excerpt_out(session, excerpt)


@router.patch("/excerpts/{excerpt_id}", response_model=ExcerptOut)
def update_excerpt(
    excerpt_id: str,
    payload: ExcerptUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> ExcerptOut:
    excerpt = session.get(Excerpt, excerpt_id)
    if excerpt is None:
        raise HTTPException(status_code=404, detail="Excerpt not found")
    data = payload.model_dump(exclude_unset=True)
    if "text" in data and data["text"]:
        excerpt.text = data["text"].strip()
        excerpt.locator = {**excerpt.locator, "edited": True}
    if "note" in data:
        excerpt.note = data["note"]
    session.flush()
    indexer.index_excerpt(session, excerpt)
    return excerpt_out(session, excerpt)


@router.delete("/excerpts/{excerpt_id}")
def delete_excerpt(excerpt_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    excerpt = session.get(Excerpt, excerpt_id)
    if excerpt is None:
        raise HTTPException(status_code=404, detail="Excerpt not found")
    indexer.remove(session, TargetType.EXCERPT, excerpt_id)
    tagging.delete_taggings_for(session, TargetType.EXCERPT, excerpt_id)
    links.delete_links_for(session, TargetType.EXCERPT, excerpt_id)
    session.delete(excerpt)
    return {"deleted": excerpt_id}


@router.get("/sources/{source_id}/locate")
def locate_text(
    source_id: str,
    session: Annotated[Session, Depends(get_db)],
    char_start: int = Query(ge=0),
) -> dict:
    """Which document unit contains a character offset (used by the reader)."""

    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    document = next(
        (d for d in source.documents if d.char_start <= char_start < max(d.char_end, d.char_start + 1)),
        None,
    )
    if document is None:
        return {"document_id": None, "locator": {}, "locator_label": ""}
    return {
        "document_id": document.id,
        "locator": document.locator,
        "locator_label": locator_label(document.locator),
        "title": document.title,
    }
