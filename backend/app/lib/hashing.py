"""Content hashing used for duplicate detection and backup manifests."""

from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK = 1024 * 1024


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """Hash of the *normalized* text.

    Whitespace is collapsed first so that the same article pasted twice with
    different line wrapping is still recognised as a near-duplicate.
    """

    collapsed = " ".join(text.split()).casefold()
    return hashlib.sha256(collapsed.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()
