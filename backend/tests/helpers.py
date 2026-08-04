"""Fixture builders shared by the tests."""

from __future__ import annotations

import io
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from minipdf import build_pdf  # noqa: E402


def text_pdf(text: str, *, title: str = "Test document", author: str = "Test Author") -> bytes:
    return build_pdf(text, title=title, author=author)


def blank_pdf() -> bytes:
    """A structurally valid PDF with no text layer - what a scan looks like."""

    return build_pdf("", title="Scanned page", author="")


def tiny_png(width: int = 8, height: int = 6, colour: tuple[int, int, int] = (200, 60, 60)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def find_span(text: str, phrase: str) -> tuple[int, int]:
    """Locate a phrase in extracted text, tolerating the hard wrapping that PDF
    extraction introduces. Returns ``(start, end)`` in the text's own offsets."""

    import re

    match = re.search(r"\s+".join(re.escape(word) for word in phrase.split()), text)
    if match is None:
        raise AssertionError(f"phrase not found in extracted text: {phrase!r}")
    return match.start(), match.end()


def upload(name: str, data: bytes, content_type: str = "application/octet-stream") -> tuple[str, tuple[str, bytes, str]]:
    """Shorthand for a multipart file field in TestClient calls."""

    return ("files", (name, data, content_type))
