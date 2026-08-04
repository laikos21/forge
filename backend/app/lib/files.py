"""Filesystem safety: sanitised names, content-addressed storage, magic sniffing.

Client-supplied filenames are never used to build a path. They are kept only as
display metadata; the bytes are stored under ``files/<hash[:2]>/<hash><ext>``.
That removes path traversal, name collisions and case-folding surprises on
Windows in one move.
"""

from __future__ import annotations

import re
from pathlib import Path

_UNSAFE = re.compile(r"[^A-Za-z0-9._ \-()\[\]]+")
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

MAGIC_SIGNATURES: list[tuple[bytes, str]] = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF87a", "image/gif"),
    (b"GIF89a", "image/gif"),
    (b"BM", "image/bmp"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]

EXTENSION_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".text": "text/plain",
    ".log": "text/plain",
    ".md": "text/markdown",
    ".markdown": "text/markdown",
    ".csv": "text/csv",
    ".tsv": "text/tab-separated-values",
    ".json": "application/json",
    ".jsonl": "application/json",
    ".vtt": "text/vtt",
    ".srt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def sanitize_filename(name: str, fallback: str = "upload") -> str:
    """Return a display-safe basename. Never used to build a storage path."""

    base = Path(name.replace("\\", "/")).name
    base = _UNSAFE.sub("_", base).strip(" .")
    if not base:
        return fallback
    stem = base.split(".")[0].upper()
    if stem in _WINDOWS_RESERVED:
        base = f"_{base}"
    return base[:180]


def extension_of(name: str) -> str:
    return Path(sanitize_filename(name)).suffix.lower()


def detect_magic(data: bytes) -> str | None:
    """MIME type from the file's own bytes, or ``None`` if unrecognised.

    Used for the checks that must not trust a client-supplied extension.
    """

    header = data[:16]
    for signature, mime in MAGIC_SIGNATURES:
        if header.startswith(signature):
            return mime
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def sniff_mime(data: bytes, fallback_extension: str = "") -> str:
    """Best-effort MIME type: magic bytes first, extension as a fallback.

    Text formats have no magic number, so the extension is the only signal
    available for them - which is why binary formats are verified with
    :func:`detect_magic` instead of this function.
    """

    return detect_magic(data) or EXTENSION_MIME.get(fallback_extension, "application/octet-stream")


def storage_relative_path(content_hash: str, extension: str) -> str:
    """Content-addressed relative path, always POSIX-style inside the DB."""

    safe_ext = extension if re.fullmatch(r"\.[A-Za-z0-9]{1,8}", extension or "") else ""
    return f"{content_hash[:2]}/{content_hash}{safe_ext}"


def resolve_within(root: Path, relative: str) -> Path:
    """Resolve ``relative`` under ``root``, refusing anything that escapes it."""

    root = root.resolve()
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path escapes the storage root")
    return candidate


def human_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"
