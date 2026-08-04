"""Dossiers: the research workspace and its export."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..domain import TargetType
from ..lib.text import slugify
from ..models import Dossier, DossierClaim, TimelineEvent
from ..schemas import (
    ClaimCreate,
    ClaimEvidenceCreate,
    ClaimUpdate,
    DossierCreate,
    DossierItemCreate,
    DossierSummary,
    DossierUpdate,
    TagsPut,
    TimelineEventCreate,
)
from ..services import dossiers as dossier_service
from ..services import export as export_service
from ..services import indexer, tagging
from .serializers import claim_out, dossier_summary

router = APIRouter(prefix="/api/dossiers", tags=["dossiers"])


def _get(session: Session, identifier: str) -> Dossier:
    dossier = session.get(Dossier, identifier)
    if dossier is None:
        dossier = session.execute(
            select(Dossier).where(Dossier.slug == identifier)
        ).scalar_one_or_none()
    if dossier is None:
        raise HTTPException(status_code=404, detail="Dossier not found")
    return dossier


@router.get("")
def list_dossiers(
    session: Annotated[Session, Depends(get_db)],
    q: str | None = None,
    status: Annotated[list[str] | None, Query()] = None,
    subject_kind: Annotated[list[str] | None, Query()] = None,
    tag: Annotated[list[str] | None, Query()] = None,
) -> dict:
    statement = select(Dossier)
    if q:
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(Dossier.title.ilike(pattern), Dossier.overview.ilike(pattern)))
    if status:
        statement = statement.where(Dossier.status.in_(status))
    if subject_kind:
        statement = statement.where(Dossier.subject_kind.in_(subject_kind))
    if tag:
        matching = tagging.targets_with_tags(session, TargetType.DOSSIER, tag)
        statement = statement.where(Dossier.id.in_(matching or ["__none__"]))
    rows = session.execute(statement.order_by(Dossier.updated_at.desc())).scalars().all()
    return {
        "items": [dossier_summary(session, d).model_dump() for d in rows],
        "total": len(rows),
    }


@router.post("", response_model=DossierSummary, status_code=201)
def create_dossier(payload: DossierCreate, session: Annotated[Session, Depends(get_db)]) -> DossierSummary:
    dossier = Dossier(
        slug=dossier_service.unique_slug(session, payload.title),
        title=payload.title,
        subject_kind=payload.subject_kind.value,
        overview=payload.overview,
        thesis=payload.thesis,
        bull_case=payload.bull_case,
        bear_case=payload.bear_case,
        risks=payload.risks,
        open_questions=payload.open_questions,
        status=payload.status.value,
        primary_entity_id=payload.primary_entity_id,
    )
    session.add(dossier)
    session.flush()
    if payload.tags:
        tagging.set_tags(session, TargetType.DOSSIER, dossier.id, payload.tags)
    indexer.index_dossier(session, dossier)
    return dossier_summary(session, dossier)


@router.get("/{identifier}")
def get_dossier(identifier: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    dossier = _get(session, identifier)
    return {
        "dossier": {
            **dossier_summary(session, dossier).model_dump(),
            "thesis": dossier.thesis,
            "bull_case": dossier.bull_case,
            "bear_case": dossier.bear_case,
            "risks": dossier.risks,
            "open_questions": dossier.open_questions,
            "primary_entity_id": dossier.primary_entity_id,
        },
        **dossier_service.detail(session, dossier),
    }


@router.patch("/{identifier}", response_model=DossierSummary)
def update_dossier(
    identifier: str,
    payload: DossierUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> DossierSummary:
    dossier = _get(session, identifier)
    data = payload.model_dump(exclude_unset=True)
    if "title" in data and data["title"] and data["title"] != dossier.title:
        dossier.title = data.pop("title")
        if slugify(dossier.title) != dossier.slug:
            dossier.slug = dossier_service.unique_slug(session, dossier.title, dossier.id)
    for field, value in data.items():
        if value is not None:
            setattr(dossier, field, value.value if hasattr(value, "value") else value)
    session.flush()
    indexer.index_dossier(session, dossier)
    return dossier_summary(session, dossier)


@router.delete("/{identifier}")
def delete_dossier(identifier: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    dossier = _get(session, identifier)
    from ..services import links

    indexer.remove(session, TargetType.DOSSIER, dossier.id)
    tagging.delete_taggings_for(session, TargetType.DOSSIER, dossier.id)
    links.delete_links_for(session, TargetType.DOSSIER, dossier.id)
    session.delete(dossier)
    return {"deleted": dossier.id}


@router.put("/{identifier}/tags")
def set_dossier_tags(
    identifier: str,
    payload: TagsPut,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    dossier = _get(session, identifier)
    tags = tagging.set_tags(session, TargetType.DOSSIER, dossier.id, payload.tags)
    return {"tags": [{"id": t.id, "slug": t.slug, "name": t.name, "color": t.color} for t in tags]}


# --- items -----------------------------------------------------------------


@router.post("/{identifier}/items", status_code=201)
def add_item(
    identifier: str,
    payload: DossierItemCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    dossier = _get(session, identifier)
    try:
        item = dossier_service.add_item(
            session,
            dossier,
            payload.target_type.value,
            payload.target_id,
            section=payload.section,
            note=payload.note,
        )
    except dossier_service.DossierError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    from ..services import refs

    return {
        "id": item.id,
        "section": item.section,
        "note": item.note,
        **refs.describe(session, item.target_type, item.target_id).as_dict(),
    }


@router.delete("/{identifier}/items/{item_id}")
def remove_item(identifier: str, item_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    dossier = _get(session, identifier)
    if not dossier_service.remove_item(session, dossier, item_id):
        raise HTTPException(status_code=404, detail="Dossier item not found")
    return {"deleted": item_id}


# --- claims ----------------------------------------------------------------


@router.post("/{identifier}/claims", status_code=201)
def add_claim(
    identifier: str,
    payload: ClaimCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    dossier = _get(session, identifier)
    claim = dossier_service.add_claim(
        session,
        dossier,
        text=payload.text,
        stance=payload.stance.value,
        confidence=payload.confidence,
        origin=payload.origin,
        generated_by=payload.generated_by,
    )
    return claim_out(session, claim)


@router.patch("/{identifier}/claims/{claim_id}")
def update_claim(
    identifier: str,
    claim_id: str,
    payload: ClaimUpdate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    dossier = _get(session, identifier)
    claim = session.get(DossierClaim, claim_id)
    if claim is None or claim.dossier_id != dossier.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(claim, field, value.value if hasattr(value, "value") else value)
    session.flush()
    return claim_out(session, claim)


@router.delete("/{identifier}/claims/{claim_id}")
def delete_claim(identifier: str, claim_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    dossier = _get(session, identifier)
    claim = session.get(DossierClaim, claim_id)
    if claim is None or claim.dossier_id != dossier.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    session.delete(claim)
    return {"deleted": claim_id}


@router.post("/{identifier}/claims/{claim_id}/evidence", status_code=201)
def add_claim_evidence(
    identifier: str,
    claim_id: str,
    payload: ClaimEvidenceCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    dossier = _get(session, identifier)
    claim = session.get(DossierClaim, claim_id)
    if claim is None or claim.dossier_id != dossier.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    try:
        evidence = dossier_service.add_evidence(
            session,
            claim,
            excerpt_id=payload.excerpt_id,
            source_id=payload.source_id,
            stance=payload.stance.value,
            note=payload.note,
        )
    except dossier_service.DossierError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"id": evidence.id, "claim_id": claim_id, "stance": evidence.stance}


@router.delete("/{identifier}/claims/{claim_id}/evidence/{evidence_id}")
def delete_claim_evidence(
    identifier: str,
    claim_id: str,
    evidence_id: str,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    from ..models import ClaimEvidence

    _get(session, identifier)
    evidence = session.get(ClaimEvidence, evidence_id)
    if evidence is None or evidence.claim_id != claim_id:
        raise HTTPException(status_code=404, detail="Evidence not found")
    session.delete(evidence)
    return {"deleted": evidence_id}


# --- timeline --------------------------------------------------------------


@router.post("/{identifier}/events", status_code=201)
def add_event(
    identifier: str,
    payload: TimelineEventCreate,
    session: Annotated[Session, Depends(get_db)],
) -> dict:
    dossier = _get(session, identifier)
    try:
        event = dossier_service.add_event(
            session,
            dossier,
            occurred_on=payload.occurred_on,
            title=payload.title,
            description=payload.description,
            kind=payload.kind,
            source_id=payload.source_id,
        )
    except dossier_service.DossierError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": event.id,
        "occurred_on": event.occurred_on.isoformat(),
        "title": event.title,
        "description": event.description,
        "kind": event.kind,
        "source_id": event.source_id,
    }


@router.delete("/{identifier}/events/{event_id}")
def delete_event(identifier: str, event_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    dossier = _get(session, identifier)
    event = session.get(TimelineEvent, event_id)
    if event is None or event.dossier_id != dossier.id:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    return {"deleted": event_id}


# --- export ----------------------------------------------------------------


@router.get("/{identifier}/export/markdown")
def export_markdown(identifier: str, session: Annotated[Session, Depends(get_db)]) -> Response:
    dossier = _get(session, identifier)
    markdown = export_service.render_dossier(session, dossier)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{dossier.slug}.md"'},
    )


@router.get("/{identifier}/export/bundle")
def export_bundle(
    identifier: str,
    session: Annotated[Session, Depends(get_db)],
    include_sources: bool = True,
) -> Response:
    dossier = _get(session, identifier)
    payload = export_service.dossier_bundle(session, dossier, include_sources=include_sources)
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{dossier.slug}-bundle.zip"'},
    )


@router.get("/{identifier}/export/preview")
def export_preview(identifier: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    dossier = _get(session, identifier)
    return {"markdown": export_service.render_dossier(session, dossier)}
