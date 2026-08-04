"""Full local backup and restore.

A backup is a plain ``.zip`` containing:

``manifest.json``   format marker, version, counts, checksum of the database
``forge.db``        a consistent copy taken with SQLite's online backup API
``export.json``     the same data as portable JSON (readable without SQLite)
``files/…``         every stored original, content-addressed

Restore is transactional at the filesystem level: the current database and file
store are moved aside into a safety backup first, and rolled back if anything
fails. Because blobs are content-addressed, merging a restored file store with
an existing one can never corrupt an unrelated source.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import text as sql

from .. import __version__
from ..config import Settings, get_settings
from ..db import get_engine, reset_engine, session_scope
from ..lib.hashing import sha256_file
from . import export as export_service

FORMAT = "forge.backup"
FORMAT_VERSION = 1
REQUIRED_TABLES = {"source", "document", "excerpt", "knowledge_object", "dossier", "search_index"}


class RestoreError(RuntimeError):
    pass


@dataclass(slots=True)
class BackupInfo:
    name: str
    path: Path
    size_bytes: int
    created_at: dt.datetime
    manifest: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "size_bytes": self.size_bytes,
            "created_at": self.created_at.isoformat(),
            "manifest": self.manifest,
        }


def _snapshot_database(destination: Path, settings: Settings) -> None:
    """Consistent copy of the live database, even with WAL active."""

    get_engine().dispose()
    source = sqlite3.connect(str(settings.db_path))
    try:
        target = sqlite3.connect(str(destination))
        try:
            source.backup(target)
            target.execute("PRAGMA journal_mode=DELETE")
            target.commit()
        finally:
            target.close()
    finally:
        source.close()


def create_backup(label: str | None = None, settings: Settings | None = None) -> BackupInfo:
    settings = settings or get_settings()
    settings.ensure_dirs()
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    safe_label = "".join(c for c in (label or "") if c.isalnum() or c in "-_")[:40]
    name = f"forge-backup-{stamp}{'-' + safe_label if safe_label else ''}.zip"
    archive_path = settings.backups_dir / name

    settings.tmp_dir.mkdir(parents=True, exist_ok=True)
    db_copy = settings.tmp_dir / f"snapshot-{stamp}.db"
    _snapshot_database(db_copy, settings)

    try:
        with session_scope() as session:
            payload = export_service.json_dump(session)
        counts = payload.get("counts", {})

        manifest = {
            "format": FORMAT,
            "format_version": FORMAT_VERSION,
            "forge_version": __version__,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "label": label or "",
            "database_sha256": sha256_file(db_copy),
            "counts": counts,
        }

        file_entries: list[dict[str, Any]] = []
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.write(db_copy, "forge.db")
            archive.writestr("export.json", json.dumps(payload, indent=2, ensure_ascii=False))
            for path in sorted(settings.files_dir.rglob("*")):
                if not path.is_file() or path.suffix == ".part":
                    continue
                relative = path.relative_to(settings.files_dir).as_posix()
                archive.write(path, f"files/{relative}")
                file_entries.append({"path": relative, "bytes": path.stat().st_size})
            manifest["files"] = file_entries
            manifest["file_count"] = len(file_entries)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
    finally:
        db_copy.unlink(missing_ok=True)

    return BackupInfo(
        name=name,
        path=archive_path,
        size_bytes=archive_path.stat().st_size,
        created_at=dt.datetime.now(dt.UTC),
        manifest=manifest,
    )


def list_backups(settings: Settings | None = None) -> list[BackupInfo]:
    settings = settings or get_settings()
    settings.ensure_dirs()
    out: list[BackupInfo] = []
    for path in sorted(settings.backups_dir.glob("*.zip"), reverse=True):
        manifest: dict[str, Any] = {}
        try:
            with zipfile.ZipFile(path) as archive:
                manifest = json.loads(archive.read("manifest.json"))
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            manifest = {"error": "unreadable or not a FORGE backup"}
        stat = path.stat()
        out.append(
            BackupInfo(
                name=path.name,
                path=path,
                size_bytes=stat.st_size,
                created_at=dt.datetime.fromtimestamp(stat.st_mtime, dt.UTC),
                manifest=manifest,
            )
        )
    return out


def backup_path(name: str, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    candidate = (settings.backups_dir / Path(name).name).resolve()
    if candidate.parent != settings.backups_dir.resolve() or not candidate.is_file():
        raise RestoreError(f"backup {name!r} not found")
    return candidate


def inspect_archive(archive_path: Path) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if "manifest.json" not in names or "forge.db" not in names:
                raise RestoreError("archive is missing manifest.json or forge.db")
            manifest = json.loads(archive.read("manifest.json"))
    except zipfile.BadZipFile as exc:
        raise RestoreError(f"not a valid zip archive: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RestoreError(f"manifest.json is not valid JSON: {exc}") from exc
    if manifest.get("format") != FORMAT:
        raise RestoreError("archive is not a FORGE backup")
    if int(manifest.get("format_version", 0)) > FORMAT_VERSION:
        raise RestoreError(
            f"backup format v{manifest['format_version']} is newer than this build supports "
            f"(v{FORMAT_VERSION})"
        )
    return manifest


def _validate_database(path: Path) -> None:
    connection = sqlite3.connect(str(path))
    try:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise RestoreError(f"restored database failed integrity check: {integrity}")
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")
        }
        missing = REQUIRED_TABLES - tables
        if missing:
            raise RestoreError(f"database is missing expected tables: {', '.join(sorted(missing))}")
    finally:
        connection.close()


def restore_backup(archive_path: Path, settings: Settings | None = None) -> dict[str, Any]:
    """Replace the current database and file store with the archive's contents."""

    settings = settings or get_settings()
    manifest = inspect_archive(archive_path)

    safety = create_backup(label="pre-restore", settings=settings)
    reset_engine()

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    staging = settings.tmp_dir / f"restore-{stamp}"
    staging.mkdir(parents=True, exist_ok=True)
    quarantine = settings.tmp_dir / f"previous-{stamp}"

    try:
        with zipfile.ZipFile(archive_path) as archive:
            for member in archive.namelist():
                normalized = member.replace("\\", "/")
                if normalized.startswith("/") or ".." in normalized.split("/"):
                    raise RestoreError(f"archive contains an unsafe path: {member!r}")
            archive.extract("forge.db", staging)
            file_members = [m for m in archive.namelist() if m.startswith("files/") and not m.endswith("/")]
            for member in file_members:
                archive.extract(member, staging)

        restored_db = staging / "forge.db"
        _validate_database(restored_db)

        quarantine.mkdir(parents=True, exist_ok=True)
        for suffix in ("", "-wal", "-shm"):
            current = Path(str(settings.db_path) + suffix)
            if current.exists():
                shutil.move(str(current), str(quarantine / current.name))
        shutil.move(str(restored_db), str(settings.db_path))

        restored_files = 0
        staged_files = staging / "files"
        if staged_files.is_dir():
            for path in staged_files.rglob("*"):
                if not path.is_file():
                    continue
                target = settings.files_dir / path.relative_to(staged_files)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
                restored_files += 1
    except Exception as exc:
        # Roll the previous database back into place before surfacing the error.
        if quarantine.is_dir():
            for path in quarantine.iterdir():
                shutil.move(str(path), str(settings.data_dir / path.name))
        shutil.rmtree(staging, ignore_errors=True)
        reset_engine()
        raise RestoreError(f"restore failed and the previous state was kept: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    shutil.rmtree(quarantine, ignore_errors=True)
    reset_engine()

    from ..migrations import upgrade_to_head

    upgrade_to_head()

    with session_scope() as session:
        counts = {
            table: int(session.execute(sql(f"SELECT count(*) FROM {table}")).scalar_one())
            for table in ("source", "excerpt", "knowledge_object", "dossier")
        }

    return {
        "restored_from": archive_path.name,
        "manifest": manifest,
        "safety_backup": safety.name,
        "files_restored": restored_files,
        "counts": counts,
    }


def delete_backup(name: str, settings: Settings | None = None) -> bool:
    path = backup_path(name, settings)
    path.unlink()
    return True
