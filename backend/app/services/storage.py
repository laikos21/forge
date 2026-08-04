"""Content-addressed blob storage for original files."""

from __future__ import annotations

from pathlib import Path

from ..config import Settings, get_settings
from ..lib.files import resolve_within, storage_relative_path


def save_blob(data: bytes, content_hash: str, extension: str, settings: Settings | None = None) -> str:
    """Write ``data`` under ``files/<hash[:2]>/<hash><ext>`` and return the
    relative path. Writing the same content twice is a no-op."""

    settings = settings or get_settings()
    relative = storage_relative_path(content_hash, extension)
    target = resolve_within(settings.files_dir, relative)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(target)
    return relative


def blob_path(relative: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    return resolve_within(settings.files_dir, relative)


def read_blob(relative: str, settings: Settings | None = None) -> bytes:
    return blob_path(relative, settings).read_bytes()


def blob_exists(relative: str | None, settings: Settings | None = None) -> bool:
    if not relative:
        return False
    try:
        return blob_path(relative, settings).is_file()
    except ValueError:
        return False


def delete_blob_if_orphan(relative: str, still_referenced: bool, settings: Settings | None = None) -> bool:
    """Delete a blob only when no other source points at the same hash."""

    if still_referenced:
        return False
    try:
        path = blob_path(relative, settings)
    except ValueError:
        return False
    if path.is_file():
        path.unlink()
        return True
    return False


def storage_stats(settings: Settings | None = None) -> dict[str, int]:
    settings = settings or get_settings()
    files = [p for p in settings.files_dir.rglob("*") if p.is_file()]
    return {
        "file_count": len(files),
        "total_bytes": sum(p.stat().st_size for p in files),
        "database_bytes": settings.db_path.stat().st_size if settings.db_path.exists() else 0,
    }
