"""Search: full-text (always on) and semantic (optional, adapter-backed)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import TargetType
from ..lib.provenance import locator_label
from ..models import Dossier, Entity, Excerpt, KnowledgeObject, Source
from ..services import indexer, refs, search, semantic, tagging
from ..services.search import HL_END, HL_START, SearchQueryError

router = APIRouter(prefix="/api/search", tags=["search"])


def _hydrate(session: Session, hit: search.SearchHit) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ref_type": hit.ref_type,
        "ref_id": hit.ref_id,
        "source_id": hit.source_id,
        "kind": hit.kind,
        "title": hit.title,
        "snippet": hit.snippet,
        "score": hit.score,
        "exists": True,
        "provenance": None,
        "subtitle": "",
    }
    if hit.ref_type == TargetType.SOURCE:
        source = session.get(Source, hit.ref_id)
        if source is None:
            payload["exists"] = False
            return payload
        payload["subtitle"] = f"{source.kind} · {source.word_count:,} words"
        payload["provenance"] = {
            "source_id": source.id,
            "source_title": source.title,
            "author": source.author,
            "published_on": source.published_on.isoformat() if source.published_on else None,
            "locator_label": "",
        }
        payload["tags"] = [t.name for t in tagging.tags_for(session, TargetType.SOURCE, source.id)]
    elif hit.ref_type == TargetType.EXCERPT:
        excerpt = session.get(Excerpt, hit.ref_id)
        if excerpt is None:
            payload["exists"] = False
            return payload
        source = session.get(Source, excerpt.source_id)
        payload["subtitle"] = f"excerpt from {source.title}" if source else "excerpt"
        payload["provenance"] = {
            "source_id": excerpt.source_id,
            "source_title": source.title if source else "(deleted source)",
            "author": source.author if source else None,
            "published_on": source.published_on.isoformat() if source and source.published_on else None,
            "locator_label": locator_label(excerpt.locator),
            "char_start": excerpt.char_start,
        }
    elif hit.ref_type == TargetType.KNOWLEDGE:
        obj = session.get(KnowledgeObject, hit.ref_id)
        if obj is None:
            payload["exists"] = False
            return payload
        payload["subtitle"] = f"{obj.kind} · {obj.status}"
        payload["origin"] = obj.origin
    elif hit.ref_type == TargetType.DOSSIER:
        dossier = session.get(Dossier, hit.ref_id)
        if dossier is None:
            payload["exists"] = False
            return payload
        payload["subtitle"] = f"{dossier.subject_kind} dossier"
        payload["slug"] = dossier.slug
    elif hit.ref_type == TargetType.ENTITY:
        entity = session.get(Entity, hit.ref_id)
        if entity is None:
            payload["exists"] = False
            return payload
        payload["subtitle"] = entity.kind
    return payload


@router.get("")
def run_search(
    session: Annotated[Session, Depends(get_db)],
    q: str,
    types: Annotated[list[str] | None, Query()] = None,
    kinds: Annotated[list[str] | None, Query()] = None,
    source_ids: Annotated[list[str] | None, Query()] = None,
    group: bool = False,
    limit: int = Query(default=40, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    try:
        hits, total = search.search_index(
            session,
            q,
            ref_types=types,
            kinds=kinds,
            source_ids=source_ids,
            limit=limit,
            offset=offset,
        )
    except SearchQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results = [_hydrate(session, hit) for hit in hits]
    payload: dict[str, Any] = {
        "query": q,
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
        "highlight": {"start": HL_START, "end": HL_END},
        "index_size": indexer.index_count(session),
    }
    if group:
        grouped = []
        for bucket in search.group_by_source(hits):
            source = session.get(Source, bucket["source_id"]) if bucket["source_id"] else None
            grouped.append(
                {
                    "key": bucket["key"],
                    "source_id": bucket["source_id"],
                    "source_title": source.title if source else None,
                    "source_kind": source.kind if source else None,
                    "best_score": bucket["best_score"],
                    "results": [_hydrate(session, hit) for hit in bucket["hits"]],
                }
            )
        payload["groups"] = grouped
    return payload


@router.get("/suggest")
def suggest(session: Annotated[Session, Depends(get_db)], q: str) -> dict:
    return {"items": search.suggest_terms(session, q)}


@router.get("/semantic")
def semantic_search(
    session: Annotated[Session, Depends(get_db)],
    q: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    state = semantic.status(session)
    if not state.enabled or not state.available:
        return {"enabled": state.enabled, "available": state.available, "detail": state.detail, "results": []}
    matches = semantic.query(session, q, limit=limit)
    results = []
    for match in matches:
        info = refs.describe(session, match["ref_type"], match["ref_id"])
        if not info.exists:
            continue
        results.append({**match, "label": info.label, "sublabel": info.sublabel, "kind": info.kind})
    return {"enabled": True, "available": True, "detail": state.detail, "results": results}


@router.post("/semantic/index")
def build_semantic_index(session: Annotated[Session, Depends(get_db)]) -> dict:
    return semantic.build_index(session)


@router.delete("/semantic/index")
def clear_semantic_index(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {"removed": semantic.clear_index(session)}


@router.get("/status")
def search_status(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {
        "fulltext": {
            "engine": "sqlite-fts5",
            "indexed_objects": indexer.index_count(session),
            "syntax": [
                {"example": "breakout base", "meaning": "all words must appear"},
                {"example": '"volume dry up"', "meaning": "exact phrase"},
                {"example": "breakout -crypto", "meaning": "exclude a word"},
                {"example": "semis*", "meaning": "prefix match"},
                {"example": "title:nvidia", "meaning": "match in the title only"},
            ],
        },
        "semantic": semantic.status(session).as_dict(),
    }


@router.post("/reindex")
def reindex(session: Annotated[Session, Depends(get_db)]) -> dict:
    counts = indexer.rebuild_all(session)
    return {"rebuilt": counts, "total": indexer.index_count(session)}
