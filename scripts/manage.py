"""FORGE maintenance CLI.

    python scripts/manage.py migrate      # bring the database to head
    python scripts/manage.py seed         # load demonstration data
    python scripts/manage.py seed --reset # rebuild demonstration data
    python scripts/manage.py demo-clear   # remove demonstration data
    python scripts/manage.py reindex      # rebuild the full-text index
    python scripts/manage.py backup       # write a backup zip
    python scripts/manage.py restore FILE # restore from a backup zip
    python scripts/manage.py info         # paths, counts, revision
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings  # noqa: E402
from app.db import session_scope  # noqa: E402
from app.migrations import current_revision, head_revision, upgrade_to_head  # noqa: E402
from app.services import backup as backup_service  # noqa: E402
from app.services import indexer, storage  # noqa: E402


def cmd_migrate(_: argparse.Namespace) -> int:
    print(f"migrated to {upgrade_to_head()}")
    return 0


def cmd_seed(args: argparse.Namespace) -> int:
    from app.seed import seed_demo_data

    upgrade_to_head()
    with session_scope() as session:
        result = seed_demo_data(session, reset=args.reset)
    print(json.dumps(result, indent=2))
    return 0


def cmd_demo_clear(_: argparse.Namespace) -> int:
    from app.seed import remove_demo_data

    with session_scope() as session:
        print(json.dumps(remove_demo_data(session), indent=2))
    return 0


def cmd_reindex(_: argparse.Namespace) -> int:
    with session_scope() as session:
        counts = indexer.rebuild_all(session)
        print(json.dumps({"rebuilt": counts, "total": indexer.index_count(session)}, indent=2))
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    info = backup_service.create_backup(args.label)
    print(f"{info.path} ({info.size_bytes:,} bytes)")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    path = Path(args.archive).resolve()
    if not path.is_file():
        print(f"not found: {path}", file=sys.stderr)
        return 1
    print(json.dumps(backup_service.restore_backup(path), indent=2))
    return 0


def cmd_info(_: argparse.Namespace) -> int:
    settings = get_settings()
    with session_scope() as session:
        index_size = indexer.index_count(session)
    print(
        json.dumps(
            {
                "data_dir": str(settings.data_dir),
                "database": str(settings.db_path),
                "revision": {"current": current_revision(), "head": head_revision()},
                "index_entries": index_size,
                "storage": storage.storage_stats(),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="manage.py", description="FORGE maintenance commands")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("migrate", help="upgrade the database to head").set_defaults(func=cmd_migrate)

    seed_parser = subparsers.add_parser("seed", help="load demonstration data")
    seed_parser.add_argument("--reset", action="store_true", help="remove existing demo data first")
    seed_parser.set_defaults(func=cmd_seed)

    subparsers.add_parser("demo-clear", help="remove demonstration data").set_defaults(func=cmd_demo_clear)
    subparsers.add_parser("reindex", help="rebuild the full-text index").set_defaults(func=cmd_reindex)

    backup_parser = subparsers.add_parser("backup", help="create a backup archive")
    backup_parser.add_argument("--label", default=None)
    backup_parser.set_defaults(func=cmd_backup)

    restore_parser = subparsers.add_parser("restore", help="restore from a backup archive")
    restore_parser.add_argument("archive")
    restore_parser.set_defaults(func=cmd_restore)

    subparsers.add_parser("info", help="show paths and counts").set_defaults(func=cmd_info)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
