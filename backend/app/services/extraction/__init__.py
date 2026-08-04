"""Format routing for the extraction layer."""

from __future__ import annotations

from ...domain import EXTENSION_KINDS, SourceKind
from ...lib.files import extension_of
from .base import DocumentUnit, ExtractedMetadata, ExtractionError, ExtractionResult
from .image import extract_image, ocr_status, reset_ocr_cache, run_ocr
from .pdf import extract_pdf
from .plain import extract_markdown, extract_text, extract_web_article, looks_like_html
from .tabular import extract_csv, extract_json
from .transcript import extract_transcript

__all__ = [
    "DocumentUnit",
    "ExtractedMetadata",
    "ExtractionError",
    "ExtractionResult",
    "extract",
    "kind_for_filename",
    "looks_like_transcript",
    "ocr_status",
    "reset_ocr_cache",
    "run_ocr",
]


def kind_for_filename(filename: str) -> SourceKind | None:
    return EXTENSION_KINDS.get(extension_of(filename))


def looks_like_transcript(text: str) -> bool:
    """Heuristic used when the user pastes without choosing a kind."""

    from .transcript import BARE_TS_RE, CUE_RE, INLINE_TS_RE

    head = text[:4000]
    if CUE_RE.search(head) or head.lstrip().upper().startswith("WEBVTT"):
        return True
    lines = [line for line in head.split("\n") if line.strip()][:40]
    if len(lines) < 2:
        return False
    stamped = sum(1 for line in lines if INLINE_TS_RE.match(line) or BARE_TS_RE.match(line))
    if stamped == len(lines):
        # Every line is timestamped: unambiguous even for a short paste.
        return True
    if len(lines) < 4:
        return False
    return stamped >= max(3, len(lines) // 3)


def extract(
    kind: SourceKind | str,
    data: bytes | str,
    filename: str | None = None,
    *,
    ocr: bool = False,
) -> ExtractionResult:
    """Dispatch to the extractor for ``kind``.

    Raises :class:`ExtractionError` for unreadable input; the ingest service
    turns that into a source in the ``error`` state rather than losing the file.
    """

    kind = SourceKind(kind)
    if kind is SourceKind.PDF:
        if isinstance(data, str):
            raise ExtractionError("PDF sources require binary content")
        return extract_pdf(data, filename)
    if kind is SourceKind.IMAGE:
        if isinstance(data, str):
            raise ExtractionError("Image sources require binary content")
        return extract_image(data, filename, ocr=ocr)
    if kind is SourceKind.CSV:
        return extract_csv(data, filename)
    if kind is SourceKind.JSON:
        return extract_json(data, filename)
    if kind is SourceKind.MARKDOWN:
        return extract_markdown(data, filename)
    if kind is SourceKind.TRANSCRIPT:
        return extract_transcript(data, filename)
    if kind is SourceKind.WEB_ARTICLE:
        return extract_web_article(data, filename)
    if kind in (SourceKind.NOTE, SourceKind.TEXT):
        if isinstance(data, bytes | bytearray):
            from .plain import decode_bytes

            decoded, _ = decode_bytes(bytes(data))
        else:
            decoded = data
        if looks_like_html(decoded):
            return extract_web_article(decoded, filename)
        return extract_markdown(decoded, filename) if kind is SourceKind.NOTE else extract_text(decoded, filename)
    raise ExtractionError(f"no extractor registered for kind {kind!r}")
