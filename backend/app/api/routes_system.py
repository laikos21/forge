"""Home, review, settings, export, backup and maintenance."""

from __future__ import annotations

import datetime as dt
import json
import sys
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import get_settings
from ..db import get_db
from ..domain import TargetType, vocabulary
from ..migrations import current_revision, head_revision
from ..models import Collection, Comparison, Dossier, Entity, Excerpt, KnowledgeObject, Source, Tag
from ..schemas import BackupCreate, ExportSourcesRequest, SeedRequest, SettingsUpdate
from ..services import backup as backup_service
from ..services import export as export_service
from ..services import indexer, refs, review, semantic, settings_store, storage
from ..services.extraction import ocr_status, reset_ocr_cache
from ..services.llm import provider_status

router = APIRouter(prefix="/api", tags=["system"])


# --- meta ------------------------------------------------------------------


@router.get("/health")
def health(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {
        "status": "ok",
        "version": __version__,
        "database": "connected",
        "migration": {"current": current_revision(), "head": head_revision()},
        "index_size": indexer.index_count(session),
        "time": dt.datetime.now(dt.UTC).isoformat(),
    }


@router.get("/meta/vocabulary")
def meta_vocabulary() -> dict:
    return vocabulary()


@router.get("/stats")
def stats(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {
        **review.home_stats(session),
        "storage": storage.storage_stats(),
        "index_size": indexer.index_count(session),
    }


@router.get("/home")
def home(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {
        "stats": review.home_stats(session),
        "recent_sources": review.recent_imports(session, days=30, limit=8),
        "recent_dossiers": review.recent_dossiers(session, limit=5),
        "unprocessed": review.unprocessed_sources(session, limit=5),
        "loose_ends": review.loose_ends(session),
    }


# --- review ----------------------------------------------------------------


@router.get("/review")
def review_dashboard(
    session: Annotated[Session, Depends(get_db)],
    days: int = Query(default=7, ge=1, le=90),
) -> dict:
    return review.dashboard(session, days)


@router.get("/review/suggestions")
def review_suggestions(
    session: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=12, ge=1, le=50),
) -> dict:
    return {
        "items": review.suggested_connections(session, limit),
        "basis": "deterministic_metadata_overlap",
        "disclaimer": (
            "These are objects that share a tag or entity and are not linked yet. "
            "No model produced them and they imply nothing about relevance."
        ),
    }


# --- settings --------------------------------------------------------------


@router.get("/settings")
def get_settings_endpoint(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {"values": settings_store.get_all(session), "schema": settings_store.schema()}


@router.put("/settings")
def update_settings(payload: SettingsUpdate, session: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        values = settings_store.set_many(session, payload.values)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    reset_ocr_cache()
    return {"values": values, "schema": settings_store.schema()}


@router.post("/settings/reset")
def reset_settings(session: Annotated[Session, Depends(get_db)]) -> dict:
    return {"values": settings_store.reset(session), "schema": settings_store.schema()}


@router.get("/settings/system")
def system_info(session: Annotated[Session, Depends(get_db)]) -> dict:
    settings = get_settings()
    ocr = ocr_status()
    return {
        "version": __version__,
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "data_dir": str(settings.data_dir),
        "database_path": str(settings.db_path),
        "files_dir": str(settings.files_dir),
        "backups_dir": str(settings.backups_dir),
        "max_upload_mb": settings.max_upload_mb,
        "migration": {"current": current_revision(), "head": head_revision()},
        "storage": storage.storage_stats(),
        "index_size": indexer.index_count(session),
        "ocr": {
            "available": ocr.available,
            "detail": ocr.reason,
            "binary": ocr.binary_path,
            "version": ocr.version,
        },
        "llm": provider_status(session).as_dict(),
        "semantic": semantic.status(session).as_dict(),
    }


# --- export ----------------------------------------------------------------


@router.get("/export/json")
def export_json(session: Annotated[Session, Depends(get_db)], download: bool = True) -> Response:
    payload = export_service.json_dump(session)
    body = json.dumps(payload, indent=2, ensure_ascii=False)
    headers = {}
    if download:
        stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
        headers["Content-Disposition"] = f'attachment; filename="forge-export-{stamp}.json"'
    return Response(content=body, media_type="application/json; charset=utf-8", headers=headers)


@router.get("/export/sources/{source_id}/markdown")
def export_source_markdown(
    source_id: str,
    session: Annotated[Session, Depends(get_db)],
    include_text: bool = True,
) -> Response:
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    from ..lib.text import slugify

    markdown = export_service.render_source(session, source, include_text=include_text)
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slugify(source.title)}.md"'},
    )


@router.get("/export/knowledge/{knowledge_id}/markdown")
def export_knowledge_markdown(knowledge_id: str, session: Annotated[Session, Depends(get_db)]) -> Response:
    obj = session.get(KnowledgeObject, knowledge_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Knowledge object not found")
    from ..lib.text import slugify

    return Response(
        content=export_service.render_knowledge(session, obj),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{obj.kind}-{slugify(obj.title)}.md"'},
    )


@router.get("/export/entities/{entity_id}/markdown")
def export_entity_markdown(entity_id: str, session: Annotated[Session, Depends(get_db)]) -> Response:
    entity = session.get(Entity, entity_id)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    from ..lib.text import slugify

    return Response(
        content=export_service.render_entity(session, entity),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{slugify(entity.name)}.md"'},
    )


@router.post("/export/sources")
def export_sources_bundle(
    payload: ExportSourcesRequest,
    session: Annotated[Session, Depends(get_db)],
) -> Response:
    missing = [
        source_id for source_id in payload.source_ids if session.get(Source, source_id) is None
    ]
    if missing:
        raise HTTPException(status_code=404, detail=f"unknown source ids: {', '.join(missing[:5])}")
    archive = export_service.sources_bundle(
        session, payload.source_ids, include_originals=payload.include_originals
    )
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="forge-sources-{stamp}.zip"'},
    )


# --- backup ----------------------------------------------------------------


@router.get("/backups")
def list_backups() -> dict:
    return {"items": [b.as_dict() for b in backup_service.list_backups()]}


@router.post("/backups", status_code=201)
def create_backup(payload: BackupCreate) -> dict:
    info = backup_service.create_backup(payload.label)
    return info.as_dict()


@router.get("/backups/{name}/download")
def download_backup(name: str) -> FileResponse:
    try:
        path = backup_service.backup_path(name)
    except backup_service.RestoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.post("/backups/{name}/restore")
def restore_backup(name: str) -> dict:
    try:
        path = backup_service.backup_path(name)
        return backup_service.restore_backup(path)
    except backup_service.RestoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/backups/upload-restore")
async def restore_uploaded_backup(file: Annotated[UploadFile, File()]) -> dict:
    settings = get_settings()
    settings.ensure_dirs()
    staging = settings.tmp_dir / f"upload-{dt.datetime.now(dt.UTC):%Y%m%d%H%M%S}.zip"
    data = await file.read()
    if len(data) > settings.max_upload_bytes * 8:
        raise HTTPException(status_code=413, detail="Backup archive is too large.")
    staging.write_bytes(data)
    try:
        return backup_service.restore_backup(staging)
    except backup_service.RestoreError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        staging.unlink(missing_ok=True)


@router.delete("/backups/{name}")
def delete_backup(name: str) -> dict:
    try:
        backup_service.delete_backup(name)
    except backup_service.RestoreError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"deleted": name}


# --- maintenance -----------------------------------------------------------


@router.post("/maintenance/reindex")
def maintenance_reindex(session: Annotated[Session, Depends(get_db)]) -> dict:
    counts = indexer.rebuild_all(session)
    return {"rebuilt": counts, "total": indexer.index_count(session)}


@router.get("/maintenance/integrity")
def maintenance_integrity(session: Annotated[Session, Depends(get_db)]) -> dict:
    """Check the invariants SQLite cannot enforce for polymorphic references."""

    from ..models import CollectionItem, ComparisonSubject, DossierItem, Link, Tagging

    dangling: list[dict[str, str]] = []

    def check(rows: list[tuple[str, str, str, str]]) -> None:
        for table, row_id, target_type, target_id in rows:
            if not refs.exists(session, target_type, target_id):
                dangling.append(
                    {"table": table, "row_id": row_id, "target_type": target_type, "target_id": target_id}
                )

    check([("tagging", r.id, r.target_type, r.target_id) for r in session.execute(select(Tagging)).scalars()])
    check([("dossier_item", r.id, r.target_type, r.target_id) for r in session.execute(select(DossierItem)).scalars()])
    check([("collection_item", r.id, r.target_type, r.target_id) for r in session.execute(select(CollectionItem)).scalars()])
    check([("comparison_subject", r.id, r.target_type, r.target_id) for r in session.execute(select(ComparisonSubject)).scalars()])
    for link in session.execute(select(Link)).scalars():
        check([("link", link.id, link.from_type, link.from_id), ("link", link.id, link.to_type, link.to_id)])

    missing_files = [
        {"source_id": s.id, "title": s.title, "path": s.storage_path}
        for s in session.execute(select(Source)).scalars()
        if s.storage_path and not storage.blob_exists(s.storage_path)
    ]

    expected = sum(
        len(session.execute(select(model)).scalars().all())
        for model in (Source, Excerpt, KnowledgeObject, Dossier, Entity)
    )
    return {
        "dangling_references": dangling,
        "missing_original_files": missing_files,
        "index": {"entries": indexer.index_count(session), "expected": expected},
        "healthy": not dangling and not missing_files and indexer.index_count(session) == expected,
    }


@router.post("/maintenance/seed")
def maintenance_seed(payload: SeedRequest, session: Annotated[Session, Depends(get_db)]) -> dict:
    from ..seed import seed_demo_data

    return seed_demo_data(session, reset=payload.reset)


@router.delete("/maintenance/demo")
def remove_demo_data(session: Annotated[Session, Depends(get_db)]) -> dict:
    from ..seed import remove_demo_data as remove

    return remove(session)


@router.get("/maintenance/refs/{target_type}/{target_id}")
def describe_ref(target_type: str, target_id: str, session: Annotated[Session, Depends(get_db)]) -> dict:
    try:
        TargetType(target_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"unknown target type {target_type!r}") from exc
    return refs.describe(session, target_type, target_id).as_dict()


@router.get("/maintenance/counts")
def maintenance_counts(session: Annotated[Session, Depends(get_db)]) -> dict:
    models = {
        "source": Source,
        "excerpt": Excerpt,
        "knowledge_object": KnowledgeObject,
        "dossier": Dossier,
        "entity": Entity,
        "tag": Tag,
        "collection": Collection,
        "comparison": Comparison,
    }
    return {name: len(session.execute(select(model)).scalars().all()) for name, model in models.items()}
