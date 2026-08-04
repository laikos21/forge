"""Plain text, Markdown and pasted web-article extraction."""

from __future__ import annotations

import datetime as dt
import re
from html.parser import HTMLParser

from ...lib.text import guess_title, normalize_text
from .base import DocumentUnit, ExtractedMetadata, ExtractionResult, assemble

MAX_UNIT_CHARS = 4000
FRONT_MATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def decode_bytes(data: bytes) -> tuple[str, str]:
    """Decode with a small, explicit ladder. Returns ``(text, encoding)``."""

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace"), "utf-8/replace"


def _chunk_paragraphs(text: str, kind: str = "chunk") -> list[DocumentUnit]:
    """Group paragraphs into units of at most ``MAX_UNIT_CHARS`` characters."""

    paragraphs = [p for p in text.split("\n\n")]
    units: list[DocumentUnit] = []
    buffer: list[str] = []
    size = 0
    index = 0
    for paragraph in paragraphs:
        if buffer and size + len(paragraph) > MAX_UNIT_CHARS:
            units.append(
                DocumentUnit(kind=kind, text="\n\n".join(buffer), locator={"block": index})
            )
            index += 1
            buffer, size = [], 0
        buffer.append(paragraph)
        size += len(paragraph) + 2
    if buffer:
        units.append(DocumentUnit(kind=kind, text="\n\n".join(buffer), locator={"block": index}))
    return units


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Minimal ``key: value`` YAML front matter (no external YAML dependency)."""

    match = FRONT_MATTER_RE.match(text)
    if not match:
        return {}, text
    data: dict[str, str] = {}
    for line in match.group(1).split("\n"):
        if ":" not in line or line.strip().startswith("#"):
            continue
        key, _, value = line.partition(":")
        data[key.strip().lower()] = value.strip().strip("\"'")
    return data, text[match.end():]


def extract_text(data: bytes | str, filename: str | None = None) -> ExtractionResult:
    raw, encoding = decode_bytes(data) if isinstance(data, bytes) else (data, "utf-8")
    text = normalize_text(raw)
    metadata = ExtractedMetadata(title=guess_title(text, filename or "Untitled text"))
    metadata.extra["encoding"] = encoding
    return assemble(_chunk_paragraphs(text), "plaintext", metadata)


def extract_markdown(data: bytes | str, filename: str | None = None) -> ExtractionResult:
    raw, encoding = decode_bytes(data) if isinstance(data, bytes) else (data, "utf-8")
    front, body = parse_front_matter(normalize_text(raw))
    text = normalize_text(body)

    units: list[DocumentUnit] = []
    current_title: str | None = None
    current_level = 0
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        chunk = "\n".join(buffer).strip("\n")
        if chunk.strip():
            units.append(
                DocumentUnit(
                    kind="section",
                    text=chunk,
                    title=current_title,
                    locator={"section": current_title or "(intro)", "level": current_level},
                )
            )

    for line in text.split("\n"):
        heading = HEADING_RE.match(line)
        if heading:
            flush()
            buffer = [line]
            current_level = len(heading.group(1))
            current_title = heading.group(2).strip()
        else:
            buffer.append(line)
    flush()
    if not units:
        units = _chunk_paragraphs(text, kind="section")

    published: dt.date | None = None
    if front.get("date"):
        try:
            published = dt.date.fromisoformat(front["date"][:10])
        except ValueError:
            published = None

    metadata = ExtractedMetadata(
        title=front.get("title") or guess_title(text, filename or "Untitled note"),
        author=front.get("author"),
        published_on=published,
        source_url=front.get("url") or front.get("source"),
    )
    metadata.extra["encoding"] = encoding
    if front:
        metadata.extra["front_matter"] = front
        if front.get("tags"):
            metadata.extra["tags"] = [t.strip() for t in re.split(r"[,;]", front["tags"]) if t.strip()]
    return assemble(units, "markdown", metadata)


class _HtmlToText(HTMLParser):
    """Tag stripper for article text pasted straight out of a browser."""

    SKIP = {"script", "style", "noscript", "svg"}
    BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self.title: str | None = None
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title = (self.title or "") + data.strip()
            return
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def looks_like_html(text: str) -> bool:
    head = text[:2000].lower()
    return "<html" in head or "<p>" in head or "<div" in head or "<article" in head


def extract_web_article(data: bytes | str, filename: str | None = None) -> ExtractionResult:
    raw, _ = decode_bytes(data) if isinstance(data, bytes) else (data, "utf-8")
    warnings: list[str] = []
    html_title: str | None = None
    if looks_like_html(raw):
        parser = _HtmlToText()
        parser.feed(raw)
        html_title = parser.title
        raw = parser.text()
        warnings.append("HTML markup was stripped; verify the extracted text before relying on it.")
    text = normalize_text(raw)
    metadata = ExtractedMetadata(title=html_title or guess_title(text, filename or "Web article"))
    return assemble(_chunk_paragraphs(text, kind="section"), "web_article", metadata, warnings)
