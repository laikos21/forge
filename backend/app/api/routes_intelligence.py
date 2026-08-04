"""Optional local intelligence endpoints.

Every response says how it was produced. Generated drafts are never written to a
user-facing field by these endpoints - the client posts the edited result back
through the normal create/update endpoints, which record ``origin=generated``.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Dossier, Generation, Source
from ..schemas import IntelligenceRequest
from ..services import settings_store
from ..services.llm import operations, provider_for, provider_status

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])


@router.get("/status")
def status(session: Annotated[Session, Depends(get_db)], probe: bool = False) -> dict:
    """Provider state. ``probe=true`` contacts the provider even when the
    feature is off, which is what the Settings "Re-check" button does."""

    preferences = settings_store.get_all(session)
    state = provider_status(session, probe=probe)
    return {
        "enabled": bool(preferences["llm.enabled"]),
        "provider": state.as_dict(),
        "model": preferences["llm.model"],
        "operations": [
            {"key": key, "label": label, "has_deterministic_fallback": key != "draft_comparison"}
            for key, label in operations.OPERATIONS.items()
        ],
        "policy": (
            "Generated output is always labelled, always editable, never overwrites your text, "
            "and is never treated as verified fact."
        ),
    }


@router.post("/run")
def run_operation(payload: IntelligenceRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    provider = provider_for(session)

    if payload.operation in {"summarize", "extract_entities", "suggest_topics", "extract_claims"}:
        source = session.get(Source, payload.source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Source not found")
        handler = {
            "summarize": operations.summarize_source,
            "extract_entities": operations.extract_entities,
            "suggest_topics": operations.suggest_topics,
            "extract_claims": operations.extract_claims,
        }[payload.operation]
        return handler(session, source, provider).as_dict()

    if payload.operation == "generate_questions":
        dossier = session.get(Dossier, payload.dossier_id)
        if dossier is None:
            raise HTTPException(status_code=404, detail="Dossier not found")
        return operations.generate_questions(session, dossier, provider).as_dict()

    return operations.draft_comparison(
        session,
        title=payload.title or "Comparison",
        subjects=payload.subjects,
        dimensions=payload.dimensions,
        provider=provider,
    ).as_dict()


@router.get("/generations")
def list_generations(session: Annotated[Session, Depends(get_db)], limit: int = 50) -> dict:
    rows = session.execute(
        select(Generation).order_by(Generation.created_at.desc()).limit(limit)
    ).scalars().all()
    return {
        "items": [
            {
                "id": g.id,
                "provider": g.provider,
                "model": g.model,
                "operation": g.operation,
                "target_type": g.target_type,
                "target_id": g.target_id,
                "accepted": g.accepted,
                "duration_ms": g.duration_ms,
                "created_at": g.created_at.isoformat(),
                "output_preview": g.output[:400],
            }
            for g in rows
        ],
        "total": len(rows),
    }


@router.post("/generations/{generation_id}/accept")
def accept(generation_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    generation = operations.accept_generation(session, generation_id)
    if generation is None:
        raise HTTPException(status_code=404, detail="Generation not found")
    return {"id": generation.id, "accepted": True}
