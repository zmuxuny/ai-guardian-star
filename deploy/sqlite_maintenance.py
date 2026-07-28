#!/usr/bin/env python3
import argparse
import os
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def _copy_and_check(source_path, target_path):
    source = sqlite3.connect(f"{source_path.resolve().as_uri()}?mode=ro", uri=True)
    target = sqlite3.connect(target_path)
    try:
        source.backup(target)
        result = target.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"SQLite integrity_check failed: {result}")
    finally:
        target.close()
        source.close()


def create_backup(database, backup_dir, retention_days=14, now=None):
    database = Path(database)
    backup_dir = Path(backup_dir)
    if not database.is_file():
        raise FileNotFoundError(database)
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    now = now or datetime.now(timezone.utc)
    backup_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    destination = backup_dir / f"guardian_users-{now:%Y%m%dT%H%M%SZ}.db"
    if destination.exists():
        raise FileExistsError(destination)

    handle = tempfile.NamedTemporaryFile(
        prefix=".guardian_users-", suffix=".tmp", dir=backup_dir, delete=False
    )
    temporary = Path(handle.name)
    handle.close()
    try:
        _copy_and_check(database, temporary)
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)

    cutoff = now.timestamp() - retention_days * 24 * 60 * 60
    for candidate in backup_dir.glob("guardian_users-*.db"):
        if candidate != destination and candidate.stat().st_mtime < cutoff:
            candidate.unlink()
    return destination


def restore_backup(backup, target):
    backup = Path(backup)
    target = Path(target)
    if not backup.is_file():
        raise FileNotFoundError(backup)
    if target.exists():
        raise FileExistsError(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        _copy_and_check(backup, temporary)
        os.chmod(temporary, 0o600)
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


def main():
    parser = argparse.ArgumentParser(description="Back up or restore guardian SQLite")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup_parser = subparsers.add_parser("backup")
    backup_parser.add_argument(
        "--database", default=os.environ.get("SQLITE_DB_PATH", "/root/guardian_users.db")
    )
    backup_parser.add_argument(
        "--backup-dir",
        default=os.environ.get("SQLITE_BACKUP_DIR", "/var/backups/wenxin"),
    )
    backup_parser.add_argument(
        "--retention-days",
        type=int,
        default=int(os.environ.get("SQLITE_BACKUP_RETENTION_DAYS", "14")),
    )

    restore_parser = subparsers.add_parser("restore")
    restore_parser.add_argument("--backup", required=True)
    restore_parser.add_argument("--target", required=True)

    args = parser.parse_args()
    if args.command == "backup":
        result = create_backup(args.database, args.backup_dir, args.retention_days)
    else:
        result = restore_backup(args.backup, args.target)
    print(result)


if __name__ == "__main__":
    main()
