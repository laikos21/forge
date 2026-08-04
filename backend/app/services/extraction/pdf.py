"""PDF extraction (pypdf, pure Python - no system binaries required)."""

from __future__ import annotations

import datetime as dt
import io
import re

from ...lib.text import guess_title, normalize_text
from .base import DocumentUnit, ExtractedMetadata, ExtractionError, ExtractionResult, assemble

PDF_DATE_RE = re.compile(r"D:(\d{4})(\d{2})(\d{2})")


def _parse_pdf_date(value: object) -> dt.date | None:
    if not value:
        return None
    match = PDF_DATE_RE.search(str(value))
    if not match:
        return None
    try:
        return dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def extract_pdf(data: bytes, filename: str | None = None) -> ExtractionResult:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise ExtractionError("pypdf is not installed") from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
    except Exception as exc:  # pypdf raises several unrelated exception types
        raise ExtractionError(f"could not open PDF: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")  # empty owner password is common for "protected" PDFs
            warnings.append("PDF was encrypted with an empty password and was opened read-only.")
        except Exception as exc:
            raise ExtractionError(f"PDF is encrypted and cannot be read: {exc}") from exc

    units: list[DocumentUnit] = []
    empty_pages = 0
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            raw = page.extract_text() or ""
        except (PdfReadError, ValueError, KeyError) as exc:
            raw = ""
            warnings.append(f"Page {page_number} could not be parsed: {exc}")
        text = normalize_text(raw)
        if not text.strip():
            empty_pages += 1
        units.append(
            DocumentUnit(
                kind="page",
                text=text,
                title=f"Page {page_number}",
                locator={"page": page_number},
            )
        )

    page_count = len(reader.pages)
    if page_count and empty_pages == page_count:
        warnings.append(
            "No embedded text found. This is probably a scanned PDF - "
            "run OCR or paste the text manually."
        )

    info = {}
    try:
        info = dict(reader.metadata or {})
    except Exception:  # pragma: no cover - malformed metadata dictionaries
        warnings.append("PDF metadata block was unreadable.")

    def meta(key: str) -> str | None:
        value = info.get(key)
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    joined = "\n\n".join(u.text for u in units if u.text.strip())
    metadata = ExtractedMetadata(
        title=meta("/Title") or guess_title(joined, filename or "Untitled PDF"),
        author=meta("/Author"),
        publisher=meta("/Producer") or meta("/Creator"),
        published_on=_parse_pdf_date(info.get("/CreationDate")),
        page_count=page_count,
    )
    metadata.extra["pdf_info"] = {k: str(v) for k, v in info.items() if v not in (None, "")}
    metadata.extra["empty_pages"] = empty_pages
    return assemble(units, "pypdf", metadata, warnings)
