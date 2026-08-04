"""Import pipeline: bytes or pasted text in, reviewable Source out.

The pipeline is intentionally linear and total - every input produces a row.
A file that cannot be parsed becomes a source in the ``error`` state with its
original bytes preserved, so nothing the user dropped is ever silently lost.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..domain import PASTE_KINDS, SourceKind, SourceStatus
from ..lib.files import detect_magic, extension_of, sanitize_filename, sniff_mime
from ..lib.hashing import sha256_bytes, sha256_text
from ..lib.text import detect_language, extractive_summary, find_dates, normalize_text, top_keywords, word_count
from ..models import Document, ImportBatch, Source
from . import entities as entity_service
from . import indexer, storage
from .extraction import ExtractionError, extract, kind_for_filename, looks_like_transcript

MAX_TEXT_CHARS = 8_000_000


class ImportRejected(ValueError):
    """Input rejected before any row was created (too large, wrong type)."""


@dataclass(slots=True)
class IngestOutcome:
    status: str  # created | duplicate | error
    source: Source | None = None
    duplicate_of: Source | None = None
    message: str = ""
    warnings: list[str] = field(default_factory=list)
    filename: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "created"


def _validate_size(data: bytes, settings: Settings) -> None:
    if len(data) > settings.max_upload_bytes:
        raise ImportRejected(
            f"File is {len(data) / 1024 / 1024:.1f} MB, over the {settings.max_upload_mb} MB limit."
        )
    if not data:
        raise ImportRejected("File is empty.")


def resolve_kind(filename: str | None, explicit: str | None, text_hint: str | None = None) -> SourceKind:
    if explicit:
        return SourceKind(explicit)
    if filename:
        detected = kind_for_filename(filename)
        if detected:
            if detected is SourceKind.TEXT and text_hint and looks_like_transcript(text_hint):
                return SourceKind.TRANSCRIPT
            return detected
    if text_hint and looks_like_transcript(text_hint):
        return SourceKind.TRANSCRIPT
    return SourceKind.TEXT


def find_duplicate(session: Session, content_hash: str, text_hash: str | None) -> Source | None:
    existing = session.execute(
        select(Source).where(Source.content_hash == content_hash).order_by(Source.created_at)
    ).scalars().first()
    if existing is not None:
        return existing
    if text_hash:
        return session.execute(
            select(Source).where(Source.text_hash == text_hash).order_by(Source.created_at)
        ).scalars().first()
    return None


def build_detected_metadata(text: str, extracted: dict[str, Any], session: Session) -> dict[str, Any]:
    candidates = entity_service.detect_candidates(session, text, extracted)
    dates = find_dates(text)
    return {
        "title": extracted.get("title"),
        "author": extracted.get("author"),
        "publisher": extracted.get("publisher"),
        "published_on": extracted.get("published_on"),
        "source_url": extracted.get("source_url"),
        "page_count": extracted.get("page_count"),
        "language": detect_language(text),
        "dates_in_text": [d.isoformat() for d in dates],
        "keywords": [word for word, _ in top_keywords(text, limit=10)],
        "tickers_detected": [c.name for c in candidates if c.kind == "ticker"],
        "companies_detected": [c.name for c in candidates if c.kind == "company"],
        "entity_candidates": [c.as_dict() for c in candidates],
        "extraction_extra": extracted.get("extra", {}),
    }


def ingest_bytes(
    session: Session,
    *,
    data: bytes,
    filename: str | None = None,
    kind: str | None = None,
    title: str | None = None,
    batch: ImportBatch | None = None,
    force: bool = False,
    ocr: bool = False,
    settings: Settings | None = None,
    origin: str = "import",
    is_demo: bool = False,
    source_url: str | None = None,
) -> IngestOutcome:
    settings = settings or get_settings()
    _validate_size(data, settings)

    display_name = sanitize_filename(filename) if filename else None
    extension = extension_of(display_name) if display_name else ""
    text_hint = None
    if extension in {".txt", ".text", ".log", ".md", ".markdown", ".vtt", ".srt"}:
        text_hint = data[:8000].decode("utf-8", errors="ignore")
    resolved_kind = resolve_kind(display_name, kind, text_hint)

    # Binary formats are verified against their own magic bytes, never against
    # the extension the client happened to send.
    magic = detect_magic(data)
    mime = magic or sniff_mime(data, extension)
    if resolved_kind is SourceKind.PDF and magic != "application/pdf":
        raise ImportRejected("File does not look like a PDF (missing %PDF- signature).")
    if resolved_kind is SourceKind.IMAGE and not (magic or "").startswith("image/"):
        raise ImportRejected("File does not look like a supported image (unrecognised signature).")

    content_hash = sha256_bytes(data)
    duplicate = None if force else find_duplicate(session, content_hash, None)
    if duplicate is not None:
        return IngestOutcome(
            status="duplicate",
            duplicate_of=duplicate,
            message=f"Identical content already imported as “{duplicate.title}”.",
            filename=display_name,
        )

    storage_path = storage.save_blob(data, content_hash, extension, settings)
    return _finish_ingest(
        session,
        data=data,
        kind=resolved_kind,
        display_name=display_name,
        title=title,
        mime=mime,
        content_hash=content_hash,
        storage_path=storage_path,
        byte_size=len(data),
        batch=batch,
        ocr=ocr,
        settings=settings,
        origin=origin,
        is_demo=is_demo,
        source_url=source_url,
    )


def ingest_text(
    session: Session,
    *,
    text: str,
    kind: str | None = None,
    title: str | None = None,
    filename: str | None = None,
    batch: ImportBatch | None = None,
    force: bool = False,
    settings: Settings | None = None,
    origin: str = "import",
    is_demo: bool = False,
    source_url: str | None = None,
    author: str | None = None,
    published_on: dt.date | None = None,
) -> IngestOutcome:
    settings = settings or get_settings()
    if not text or not text.strip():
        raise ImportRejected("Pasted content is empty.")
    if len(text) > MAX_TEXT_CHARS:
        raise ImportRejected(f"Pasted content exceeds {MAX_TEXT_CHARS:,} characters.")

    resolved_kind = resolve_kind(filename, kind, text)
    if resolved_kind not in PASTE_KINDS and resolved_kind not in {SourceKind.CSV, SourceKind.JSON}:
        raise ImportRejected(f"{resolved_kind} sources must be uploaded as a file, not pasted.")

    data = text.encode("utf-8")
    _validate_size(data, settings)
    content_hash = sha256_bytes(data)
    text_hash = sha256_text(normalize_text(text))
    duplicate = None if force else find_duplicate(session, content_hash, text_hash)
    if duplicate is not None:
        same = "Identical" if duplicate.content_hash == content_hash else "Near-identical"
        return IngestOutcome(
            status="duplicate",
            duplicate_of=duplicate,
            message=f"{same} content already imported as “{duplicate.title}”.",
        )

    extension = {
        SourceKind.MARKDOWN: ".md",
        SourceKind.NOTE: ".md",
        SourceKind.CSV: ".csv",
        SourceKind.JSON: ".json",
        SourceKind.TRANSCRIPT: ".txt",
    }.get(resolved_kind, ".txt")
    storage_path = storage.save_blob(data, content_hash, extension, settings)

    return _finish_ingest(
        session,
        data=text,
        kind=resolved_kind,
        display_name=sanitize_filename(filename) if filename else None,
        title=title,
        mime="text/plain",
        content_hash=content_hash,
        storage_path=storage_path,
        byte_size=len(data),
        batch=batch,
        ocr=False,
        settings=settings,
        origin=origin,
        is_demo=is_demo,
        source_url=source_url,
        author=author,
        published_on=published_on,
    )


def _finish_ingest(
    session: Session,
    *,
    data: bytes | str,
    kind: SourceKind,
    display_name: str | None,
    title: str | None,
    mime: str,
    content_hash: str,
    storage_path: str,
    byte_size: int,
    batch: ImportBatch | None,
    ocr: bool,
    settings: Settings,
    origin: str,
    is_demo: bool,
    source_url: str | None = None,
    author: str | None = None,
    published_on: dt.date | None = None,
) -> IngestOutcome:
    source = Source(
        kind=str(kind),
        status=str(SourceStatus.PROCESSING),
        title=title or display_name or "Untitled source",
        original_filename=display_name,
        storage_path=storage_path,
        mime_type=mime,
        byte_size=byte_size,
        content_hash=content_hash,
        batch_id=batch.id if batch else None,
        origin=origin,
        is_demo=is_demo,
        source_url=source_url,
        author=author,
        published_on=published_on,
    )
    session.add(source)
    session.flush()

    try:
        result = extract(kind, data, display_name, ocr=ocr)
    except ExtractionError as exc:
        source.status = str(SourceStatus.ERROR)
        source.error_message = str(exc)
        source.text = ""
        source.extraction_method = "failed"
        session.flush()
        indexer.index_source(session, source)
        return IngestOutcome(
            status="error",
            source=source,
            message=f"Could not extract content: {exc}",
            filename=display_name,
        )

    text = normalize_text(result.text)
    source.text = text
    source.text_hash = sha256_text(text) if text else None
    source.char_count = len(text)
    source.word_count = word_count(text)
    source.extraction_method = result.method
    source.extraction_warnings = list(result.warnings)
    source.page_count = result.metadata.page_count

    extracted = result.metadata.as_dict()
    detected = build_detected_metadata(text, extracted, session)
    source.detected_metadata = detected
    source.language = detected.get("language")
    source.summary = extractive_summary(text) if text else ""

    if not title:
        source.title = (extracted.get("title") or display_name or source.title)[:500]
    if not source.author and extracted.get("author"):
        source.author = str(extracted["author"])[:300]
    if not source.publisher and extracted.get("publisher"):
        source.publisher = str(extracted["publisher"])[:300]
    if not source.source_url and extracted.get("source_url"):
        source.source_url = str(extracted["source_url"])[:2000]
    if not source.published_on and extracted.get("published_on"):
        try:
            source.published_on = dt.date.fromisoformat(str(extracted["published_on"])[:10])
        except ValueError:
            pass

    for unit in result.units:
        session.add(
            Document(
                source_id=source.id,
                ordinal=unit.ordinal,
                kind=unit.kind,
                title=unit.title,
                text=unit.text,
                char_start=unit.char_start,
                char_end=unit.char_end,
                locator=unit.locator,
            )
        )

    source.status = str(SourceStatus.NEEDS_REVIEW)
    session.flush()
    indexer.index_source(session, source)

    return IngestOutcome(
        status="created",
        source=source,
        message="Imported.",
        warnings=list(result.warnings),
        filename=display_name,
    )


def mark_reviewed(session: Session, source: Source, *, confirmed_entities: list[dict[str, Any]] | None = None) -> Source:
    if confirmed_entities:
        entity_service.attach_entities(session, source, confirmed_entities)
    source.status = str(SourceStatus.READY)
    source.reviewed_at = dt.datetime.now(dt.UTC)
    session.flush()
    indexer.index_source(session, source)
    return source


def reprocess(session: Session, source: Source, *, ocr: bool = False, settings: Settings | None = None) -> IngestOutcome:
    """Re-run extraction on a stored original (e.g. after enabling OCR)."""

    settings = settings or get_settings()
    if not source.storage_path or not storage.blob_exists(source.storage_path, settings):
        return IngestOutcome(status="error", source=source, message="Original file is no longer available.")

    data = storage.read_blob(source.storage_path, settings)
    kind = SourceKind(source.kind)
    payload: bytes | str = data
    if kind not in {SourceKind.PDF, SourceKind.IMAGE}:
        payload = data.decode("utf-8", errors="replace")

    try:
        result = extract(kind, payload, source.original_filename, ocr=ocr)
    except ExtractionError as exc:
        source.status = str(SourceStatus.ERROR)
        source.error_message = str(exc)
        session.flush()
        return IngestOutcome(status="error", source=source, message=str(exc))

    for document in list(source.documents):
        session.delete(document)
    session.flush()

    text = normalize_text(result.text)
    source.text = text
    source.text_hash = sha256_text(text) if text else None
    source.char_count = len(text)
    source.word_count = word_count(text)
    source.extraction_method = result.method
    source.extraction_warnings = list(result.warnings)
    source.error_message = None
    source.detected_metadata = build_detected_metadata(text, result.metadata.as_dict(), session)
    source.summary = extractive_summary(text) if text else ""
    source.status = str(SourceStatus.NEEDS_REVIEW)
    for unit in result.units:
        session.add(
            Document(
                source_id=source.id,
                ordinal=unit.ordinal,
                kind=unit.kind,
                title=unit.title,
                text=unit.text,
                char_start=unit.char_start,
                char_end=unit.char_end,
                locator=unit.locator,
            )
        )
    session.flush()
    indexer.index_source(session, source)
    return IngestOutcome(status="created", source=source, message="Reprocessed.", warnings=result.warnings)
