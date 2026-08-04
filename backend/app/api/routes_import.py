"""Inbox: file upload, paste import, review."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..domain import SourceStatus, TargetType
from ..models import ImportBatch, Source
from ..schemas import (
    ImportItemResult,
    ImportResponse,
    ReviewRequest,
    SourceSummary,
    TextImportRequest,
)
from ..services import ingest, settings_store, tagging
from ..services.extraction import ocr_status
from ..services.ingest import ImportRejected
from .serializers import source_summaries, source_summary

router = APIRouter(prefix="/api", tags=["inbox"])


def _result_from_outcome(outcome: ingest.IngestOutcome) -> ImportItemResult:
    if outcome.status == "duplicate" and outcome.duplicate_of is not None:
        return ImportItemResult(
            status="duplicate",
            filename=outcome.filename,
            message=outcome.message,
            duplicate_of_id=outcome.duplicate_of.id,
            duplicate_of_title=outcome.duplicate_of.title,
        )
    source = outcome.source
    return ImportItemResult(
        status="created" if outcome.status == "created" else "error",
        filename=outcome.filename,
        source_id=source.id if source else None,
        title=source.title if source else None,
        message=outcome.message,
        warnings=outcome.warnings,
    )


def _tally(response: ImportResponse) -> ImportResponse:
    response.created = sum(1 for r in response.results if r.status == "created")
    response.duplicates = sum(1 for r in response.results if r.status == "duplicate")
    response.errors = sum(1 for r in response.results if r.status == "error")
    response.rejected = sum(1 for r in response.results if r.status == "rejected")
    return response


def _auto_review(session: Session, source: Source) -> None:
    if settings_store.get(session, "import.auto_review"):
        ingest.mark_reviewed(session, source)


@router.post("/import/files", response_model=ImportResponse)
async def import_files(
    session: Annotated[Session, Depends(get_db)],
    files: Annotated[list[UploadFile], File(description="One or more files to import")],
    kind: Annotated[str | None, Form()] = None,
    force: Annotated[bool, Form()] = False,
    batch_label: Annotated[str | None, Form()] = None,
) -> ImportResponse:
    settings = get_settings()
    if not files:
        raise HTTPException(status_code=400, detail="No files were uploaded.")
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=400,
            detail=f"Batch is limited to {settings.max_batch_files} files ({len(files)} sent).",
        )

    batch = ImportBatch(label=batch_label or f"Upload {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M}")
    session.add(batch)
    session.flush()

    use_ocr = bool(settings_store.get(session, "import.ocr_images")) and ocr_status().available
    response = ImportResponse(batch_id=batch.id)

    for upload in files:
        data = await upload.read()
        try:
            outcome = ingest.ingest_bytes(
                session,
                data=data,
                filename=upload.filename,
                kind=kind or None,
                batch=batch,
                force=force,
                ocr=use_ocr,
                settings=settings,
            )
        except ImportRejected as exc:
            response.results.append(
                ImportItemResult(status="rejected", filename=upload.filename, message=str(exc))
            )
            continue
        except ValueError as exc:
            response.results.append(
                ImportItemResult(status="rejected", filename=upload.filename, message=str(exc))
            )
            continue
        if outcome.source is not None and outcome.status == "created":
            _auto_review(session, outcome.source)
        response.results.append(_result_from_outcome(outcome))

    return _tally(response)


@router.post("/import/text", response_model=ImportResponse)
def import_text(
    payload: TextImportRequest,
    session: Annotated[Session, Depends(get_db)],
) -> ImportResponse:
    batch = None
    if payload.batch_label:
        batch = ImportBatch(label=payload.batch_label)
        session.add(batch)
        session.flush()

    try:
        outcome = ingest.ingest_text(
            session,
            text=payload.text,
            kind=payload.kind.value if payload.kind else None,
            title=payload.title,
            filename=payload.filename,
            batch=batch,
            force=payload.force,
            source_url=payload.source_url,
            author=payload.author,
            published_on=payload.published_on,
        )
    except ImportRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if outcome.source is not None and payload.tags:
        tagging.set_tags(session, TargetType.SOURCE, outcome.source.id, payload.tags)
    if outcome.source is not None and outcome.status == "created":
        _auto_review(session, outcome.source)

    response = ImportResponse(batch_id=batch.id if batch else None, results=[_result_from_outcome(outcome)])
    return _tally(response)


@router.get("/inbox")
def inbox(session: Annotated[Session, Depends(get_db)]) -> dict:
    pending = session.execute(
        select(Source)
        .where(Source.status.in_([str(SourceStatus.NEEDS_REVIEW), str(SourceStatus.PROCESSING)]))
        .order_by(Source.imported_at.desc())
    ).scalars().all()
    failed = session.execute(
        select(Source).where(Source.status == str(SourceStatus.ERROR)).order_by(Source.imported_at.desc())
    ).scalars().all()
    recent_batches = session.execute(
        select(ImportBatch).order_by(ImportBatch.created_at.desc()).limit(5)
    ).scalars().all()

    return {
        "pending": [s.model_dump() for s in source_summaries(session, pending)],
        "failed": [s.model_dump() for s in source_summaries(session, failed)],
        "batches": [
            {
                "id": batch.id,
                "label": batch.label,
                "created_at": batch.created_at.isoformat(),
                "source_count": len(batch.sources),
            }
            for batch in recent_batches
        ],
        "ocr": {
            "available": ocr_status().available,
            "detail": ocr_status().reason,
            "enabled": bool(settings_store.get(session, "import.ocr_images")),
        },
        "limits": {
            "max_upload_mb": get_settings().max_upload_mb,
            "max_batch_files": get_settings().max_batch_files,
        },
    }


@router.get("/sources/{source_id}/review")
def review_payload(source_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    detected = source.detected_metadata or {}
    return {
        "source": source_summary(session, source).model_dump(),
        "detected": detected,
        "entity_candidates": detected.get("entity_candidates", []),
        "warnings": source.extraction_warnings or [],
        "preview": source.text[:4000],
        "documents": len(source.documents),
    }


@router.post("/sources/{source_id}/review", response_model=SourceSummary)
def submit_review(
    source_id: str,
    payload: ReviewRequest,
    session: Annotated[Session, Depends(get_db)],
) -> SourceSummary:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    for field in ("title", "author", "publisher", "source_url", "published_on", "language", "summary", "review_notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(source, field, value)
    if payload.tags is not None:
        tagging.set_tags(session, TargetType.SOURCE, source.id, payload.tags)

    ingest.mark_reviewed(
        session,
        source,
        confirmed_entities=[c.model_dump() for c in payload.confirmed_entities],
    )
    return source_summary(session, source)


@router.post("/sources/{source_id}/reprocess", response_model=SourceSummary)
def reprocess_source(
    source_id: str,
    session: Annotated[Session, Depends(get_db)],
    ocr: bool = False,
) -> SourceSummary:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if ocr and not ocr_status().available:
        raise HTTPException(status_code=409, detail=ocr_status().reason)
    outcome = ingest.reprocess(session, source, ocr=ocr)
    if outcome.status == "error":
        raise HTTPException(status_code=422, detail=outcome.message)
    return source_summary(session, source)
