"""A tiny, dependency-free PDF writer used to generate the sample documents.

FORGE reads PDFs; it does not need to write them. This exists only so the
repository can ship a *real* PDF fixture (with a real text layer, real metadata
and real page boundaries) instead of a stub that the extractor never sees.

Supports: multiple pages, Helvetica, WinAnsi text, a document info dictionary.
"""

from __future__ import annotations

import datetime as dt

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
MARGIN_X, MARGIN_TOP = 56, 748
LEADING = 15
FONT_SIZE = 10.5
MAX_CHARS = 92
LINES_PER_PAGE = 44


def _escape(text: str) -> bytes:
    encoded = text.encode("cp1252", errors="replace")
    out = bytearray()
    for byte in encoded:
        if byte in (0x28, 0x29, 0x5C):  # ( ) \
            out.append(0x5C)
        out.append(byte)
    return bytes(out)


def wrap(text: str, width: int = MAX_CHARS) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if not paragraph.strip():
            lines.append("")
            continue
        current = ""
        for word in paragraph.split():
            candidate = f"{current} {word}".strip()
            if len(candidate) > width and current:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
    return lines


def paginate(text: str, lines_per_page: int = LINES_PER_PAGE) -> list[list[str]]:
    lines = wrap(text)
    pages: list[list[str]] = []
    for start in range(0, max(len(lines), 1), lines_per_page):
        pages.append(lines[start : start + lines_per_page])
    return pages or [[""]]


def _content_stream(lines: list[str]) -> bytes:
    body = bytearray(b"BT\n")
    body += f"/F1 {FONT_SIZE} Tf\n".encode("ascii")
    body += f"{LEADING} TL\n".encode("ascii")
    body += f"{MARGIN_X} {MARGIN_TOP} Td\n".encode("ascii")
    for line in lines:
        body += b"(" + _escape(line) + b") Tj\nT*\n"
    body += b"ET\n"
    return bytes(body)


def build_pdf(text: str, *, title: str, author: str = "", subject: str = "",
              created: dt.date | None = None) -> bytes:
    pages = paginate(text)
    created = created or dt.date.today()

    objects: dict[int, bytes] = {}
    page_object_ids = [5 + index * 2 for index in range(len(pages))]

    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{oid} 0 R" for oid in page_object_ids)
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii")
    objects[3] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    stamp = created.strftime("%Y%m%d") + "000000Z"
    info = (
        f"<< /Title ({title}) /Author ({author}) /Subject ({subject}) "
        f"/Producer (FORGE sample generator) /CreationDate (D:{stamp}) >>"
    )
    objects[4] = info.encode("cp1252", errors="replace")

    for index, lines in enumerate(pages):
        page_id = page_object_ids[index]
        content_id = page_id + 1
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH} {PAGE_HEIGHT}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>"
        ).encode("ascii")
        stream = _content_stream(lines)
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode("ascii") + objects[number] + b"\nendobj\n"

    xref_offset = len(out)
    highest = max(objects)
    out += f"xref\n0 {highest + 1}\n".encode("ascii")
    out += b"0000000000 65535 f \n"
    for number in range(1, highest + 1):
        if number in offsets:
            out += f"{offsets[number]:010d} 00000 n \n".encode("ascii")
        else:  # unused slot (never happens with the numbering above)
            out += b"0000000000 65535 f \n"
    out += (
        f"trailer\n<< /Size {highest + 1} /Root 1 0 R /Info 4 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n"
    ).encode("ascii")
    return bytes(out)
