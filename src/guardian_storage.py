"""Explicit storage ownership and bounded calendar retention.

Filesystem and SQLite operations are not one atomic transaction. Failed deletion
keeps a pending_delete index row for retry. This is not a power-loss guarantee.
"""
import json
import math
import os
import shutil
import stat
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath

MARKER_NAME = ".guardian-recording-root.json"
SHANGHAI = timezone(timedelta(hours=8), "Asia/Shanghai")


def _root(config):
    if not config.enabled or config.data_root is None:
        raise ValueError("recording storage is disabled or unconfigured")
    root = Path(config.data_root)
    if os.path.normcase(str(root.absolute())) != os.path.normcase(str(root.resolve())):
        raise ValueError("storage root or its ancestors must not be symlinks/junctions")
    return root


def _identity(root):
    info = root.stat()
    return {"device": info.st_dev, "inode": info.st_ino}


def _same_device_info(path, root_device):
    info = path.stat()
    if info.st_dev != root_device:
        raise ValueError("managed path crosses a filesystem device boundary")
    return info


def initialize_storage(config):
    """Explicitly claim an empty root only; never adopt unknown existing data."""
    root = _root(config)
    if root.exists():
        if not root.is_dir():
            raise ValueError("storage root is not a directory")
        if (root / MARKER_NAME).exists():
            return validate_storage(config)
        if any(root.iterdir()):
            raise ValueError("refusing to claim nonempty unowned storage")
    else:
        # Caller must explicitly create/verify the mount parent first.
        if not root.parent.is_dir():
            raise ValueError("storage root parent must already exist")
        root.mkdir()
    marker = {"version": 1, "id": uuid.uuid4().hex,
              "root": str(root.resolve()), "identity": _identity(root)}
    with (root / MARKER_NAME).open("x", encoding="utf-8") as stream:
        json.dump(marker, stream)
        stream.flush()
        os.fsync(stream.fileno())
    for name in ("db", "recordings", "snapshots", "tmp"):
        (root / name).mkdir()
    return validate_storage(config)


def validate_storage(config):
    """Read-only validation: no creation, migration, directory or marker repair."""
    root = _root(config)
    if not root.is_dir():
        raise ValueError("managed storage root is absent")
    root_device = root.stat().st_dev
    marker_path = root / MARKER_NAME
    if marker_path.is_symlink() or not marker_path.is_file():
        raise ValueError("managed storage marker is absent or unsafe")
    if _same_device_info(marker_path, root_device).st_size > 4096:
        raise ValueError("managed storage marker is invalid")
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("managed storage marker cannot be read") from exc
    if (not isinstance(marker, dict) or marker.get("version") != 1
            or not isinstance(marker.get("id"), str) or len(marker["id"]) != 32
            or marker.get("root") != str(root.resolve())
            or marker.get("identity") != _identity(root)):
        raise ValueError("managed storage identity mismatch")
    for name in ("db", "recordings", "snapshots", "tmp"):
        path = root / name
        if not path.is_dir() or path.is_symlink() or path.resolve().parent != root.resolve():
            raise ValueError("managed storage directory is absent or unsafe")
        _same_device_info(path, root_device)
    return marker


def safe_managed_path(config, relpath, must_exist=False):
    """Accept only simple POSIX relative media paths beneath managed directories.

    Caller must prevent untrusted users from modifying this private storage tree;
    checks cannot remove the platform filesystem's TOCTOU race by themselves.
    Device checks reject ordinary child mounts, but cannot identify same-device
    bind mounts. Deployment must separately validate mount topology on the board.
    """
    validate_storage(config)
    if not isinstance(relpath, str) or not relpath or "\\" in relpath or ":" in relpath:
        raise ValueError("invalid managed relative path")
    relative = PurePosixPath(relpath)
    if relative.is_absolute() or any(part in (".", "..", "") for part in relpath.split("/")):
        raise ValueError("managed path traversal is forbidden")
    if relative.parts[0] not in ("recordings", "snapshots", "tmp", "db") or len(relative.parts) < 2:
        raise ValueError("path must be in a managed subdirectory")
    root = Path(config.data_root)
    root_device = root.stat().st_dev
    path = root.joinpath(*relative.parts)
    for candidate in (path,) + tuple(path.parents):
        if candidate == root:
            break
        if candidate.is_symlink():
            raise ValueError("managed path contains a symlink")
        try:
            _same_device_info(candidate, root_device)
        except FileNotFoundError:
            pass
    resolved = path.resolve()
    if root.resolve() not in resolved.parents:
        raise ValueError("managed path escapes storage root")
    if path.exists():
        info = _same_device_info(path, root_device)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink > 1:
            raise ValueError("managed file must be regular and not hard-linked")
    elif must_exist:
        raise FileNotFoundError("managed file is absent")
    return path


def managed_usage(config):
    validate_storage(config)
    total = 0
    root = Path(config.data_root)
    root_device = root.stat().st_dev
    def fail_walk(error):
        raise error
    for directory, dirs, files in os.walk(str(root), followlinks=False, onerror=fail_walk):
        _same_device_info(Path(directory), root_device)
        for name in dirs:
            path = Path(directory) / name
            if path.is_symlink() or path.resolve().parent != Path(directory).resolve():
                raise ValueError("unsafe directory in managed storage")
            _same_device_info(path, root_device)
        for name in files:
            path = Path(directory) / name
            if path.is_symlink():
                raise ValueError("unsafe file in managed storage")
            info = _same_device_info(path, root_device)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("nonregular file in managed storage")
            total += info.st_size
    return total


def storage_status(config):
    if not config.enabled:
        return {"enabled": False, "state": "disabled"}
    validate_storage(config)
    usage = shutil.disk_usage(str(config.data_root))
    used = managed_usage(config)
    return {"enabled": True, "state": "ready", "used_bytes": used,
            "free_bytes": usage.free, "total_bytes": usage.total,
            "quota_bytes": config.storage_quota_bytes, "min_free_bytes": config.min_free_bytes,
            "can_record": used < config.storage_quota_bytes and usage.free > config.min_free_bytes}


def retention_cutoff(config, now):
    if type(now) not in (float, int) or not math.isfinite(now):
        raise ValueError("invalid UTC timestamp")
    local = datetime.fromtimestamp(now, SHANGHAI)
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return (midnight - timedelta(days=config.retention_days - 1)).timestamp()


def _finite_number(value):
    # SQLite's dynamic typing may return text even for a REAL-affinity column.
    return type(value) in (int, float) and math.isfinite(value)


def _valid_interval(row, allow_open=False):
    start, end = row["started_at"], row["ended_at"]
    if not _finite_number(start):
        return False
    if end is None and allow_open:
        return True
    return _finite_number(end) and start <= end


def cleanup_expired(store, now=None, time_trusted=False, dry_run=False):
    """Remove only indexed, completed, fully expired media; never recurse-delete."""
    summary = {"deleted": 0, "events_deleted": 0, "gaps_deleted": 0,
               "candidates": 0, "errors": [], "skipped": None}
    if not store.config.enabled:
        summary["skipped"] = "disabled"
        return summary
    if time_trusted is not True:
        summary["skipped"] = "untrusted_time"
        return summary
    now = time.time() if now is None else now
    cutoff = retention_cutoff(store.config, now)
    # A board without a synchronized clock often boots near epoch zero.
    if not 2020 <= datetime.fromtimestamp(now, SHANGHAI).year <= 2100:
        summary["skipped"] = "implausible_time"
        return summary
    validate_storage(store.config)
    with store._write_lock:
        previous = store._get_meta("last_cleanup_at")
        if previous is not None:
            try:
                previous = float(previous)
            except (TypeError, ValueError):
                previous = float("nan")
            if not math.isfinite(previous):
                summary["skipped"] = "invalid_clock_state"
                return summary
            if now < previous:
                summary["skipped"] = "clock_rollback"
                return summary
        rows = store._query(
            "SELECT * FROM recordings WHERE state IN ('complete','pending_delete')")
        for row in rows:
            # Never let SQL affinity/coercion make a corrupt row deletable.
            if (not _valid_interval(row) or not _finite_number(row["lease_until"])
                    or row["lease_until"] < 0):
                summary["errors"].append({"id": row["id"], "error": "invalid_recording_interval_or_lease"})
                continue
            if not (row["started_at"] < cutoff and row["ended_at"] <= cutoff
                    and row["lease_until"] <= now):
                continue
            summary["candidates"] += 1
            if dry_run:
                continue
            # safe path validation happens before marking or unlinking anything.
            try:
                if not row["relpath"].startswith(("recordings/", "tmp/")):
                    raise ValueError("cleanup only manages indexed video media")
                path = safe_managed_path(store.config, row["relpath"])
                store._execute("UPDATE recordings SET state='pending_delete' WHERE id=?", (row["id"],))
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
                store._execute("DELETE FROM recordings WHERE id=? AND state='pending_delete'", (row["id"],))
                summary["deleted"] += 1
            except (OSError, ValueError) as exc:
                summary["errors"].append({"id": row["id"], "error": type(exc).__name__})
                try:
                    store._execute("UPDATE recordings SET error=? WHERE id=?", (type(exc).__name__, row["id"]))
                except Exception:
                    # Preserve original failure; no open connection survives _execute.
                    summary["errors"].append({"id": row["id"], "error": "error_record_failed"})
        # Open/cross-boundary events stay visible; validate corrupt index rows too.
        for table in ("events", "gaps"):
            for row in store._query("SELECT id,started_at,ended_at FROM " + table):
                if not _valid_interval(row, allow_open=True):
                    summary["errors"].append({"id": row["id"], "error": "invalid_" + table + "_interval"})
                    continue
                if (row["ended_at"] is not None and row["started_at"] < cutoff
                        and row["ended_at"] <= cutoff and not dry_run):
                    summary[table + "_deleted"] += store._execute(
                        "DELETE FROM " + table + " WHERE id=?", (row["id"],))
        if not dry_run:
            store._set_meta("last_cleanup_at", str(now))
    return summary
