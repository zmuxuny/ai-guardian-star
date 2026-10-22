"""Local SQLite history with short connections and one coordinated writer.

Creating an enabled store explicitly creates its schema in an already managed
root. Disabled construction does not read/create any directory or database.
"""
import json
import math
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager

from guardian_storage import managed_usage, safe_managed_path, validate_storage

_LOCKS = {}
_LOCKS_LOCK = threading.Lock()
HISTORY_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,128}")


def validate_history_id(value):
    """Stable IDs must remain addressable through the public ID-only routes."""
    if not isinstance(value, str) or HISTORY_ID_PATTERN.fullmatch(value) is None:
        raise ValueError("invalid history id")
    return value


def validate_event_kind(value):
    """Kind is bound text, not an identifier: Unicode and spaces are allowed."""
    if not isinstance(value, str) or not value or len(value) > 100:
        raise ValueError("invalid event kind")
    return value


def _timestamp(value, optional=False):
    if value is None and optional:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("timestamp must be finite UTC Unix seconds")
    return float(value)


def _json(value):
    encoded = json.dumps({} if value is None else value, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > 65536:
        raise ValueError("history JSON exceeds 64 KiB")
    return encoded


class HistoryStore:
    def __init__(self, config):
        self.config = config
        self._closed = False
        self._db_path = None
        self._marker_id = None
        self._db_identity = None
        with _LOCKS_LOCK:
            self._write_lock = _LOCKS.setdefault(os.path.normcase(str(config.data_root)), threading.RLock())
        if not config.enabled:
            return
        self._marker_id = validate_storage(config)["id"]
        self._db_path = safe_managed_path(config, "db/history.db")
        with self._write_lock, self._connection() as db:
            actual = db.execute("PRAGMA journal_mode=" + config.journal_mode).fetchone()[0]
            if actual.upper() != config.journal_mode:
                raise RuntimeError("SQLite journal mode was not applied")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("unsupported history schema version")
            if version == 0 and db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone():
                raise ValueError("refusing to adopt an unknown existing database")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS recordings (
                    id TEXT PRIMARY KEY, relpath TEXT NOT NULL UNIQUE,
                    started_at REAL NOT NULL, ended_at REAL,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL CHECK(state IN ('recording','complete','failed','pending_delete')),
                    error TEXT, metadata TEXT NOT NULL DEFAULT '{}',
                    lease_until REAL NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS recording_time ON recordings(started_at,ended_at);
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, started_at REAL NOT NULL,
                    ended_at REAL, person_id TEXT, payload TEXT NOT NULL,
                    metadata TEXT NOT NULL DEFAULT '{}');
                CREATE INDEX IF NOT EXISTS event_time ON events(started_at,ended_at);
                CREATE TABLE IF NOT EXISTS gaps (
                    id TEXT PRIMARY KEY, started_at REAL NOT NULL,
                    ended_at REAL, reason TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS event_recordings (
                    event_id TEXT NOT NULL, recording_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (event_id, recording_id));
                CREATE INDEX IF NOT EXISTS event_recording_event ON event_recordings(event_id);
                CREATE INDEX IF NOT EXISTS event_recording_recording ON event_recordings(recording_id);
                CREATE TABLE IF NOT EXISTS history_meta (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                PRAGMA user_version=1;
            """)
        info = self._db_path.stat()
        self._db_identity = (info.st_dev, info.st_ino)

    @contextmanager
    def _connection(self):
        if self._closed or not self.config.enabled:
            raise RuntimeError("history store is disabled or closed")
        if validate_storage(self.config)["id"] != self._marker_id:
            raise ValueError("storage ownership changed")
        path = safe_managed_path(self.config, "db/history.db")
        if self._db_path is not None and path != self._db_path:
            raise ValueError("history database path changed")
        if self._db_identity is not None:
            info = path.stat()
            if (info.st_dev, info.st_ino) != self._db_identity:
                raise ValueError("history database identity changed")
        db = sqlite3.connect(str(path), timeout=5.0)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA busy_timeout=5000")
            db.execute("PRAGMA synchronous=" + self.config.synchronous)
            expected_sync = {"FULL": 2, "EXTRA": 3}[self.config.synchronous]
            if db.execute("PRAGMA synchronous").fetchone()[0] != expected_sync:
                raise RuntimeError("SQLite synchronous mode was not applied")
            with db:
                yield db
        finally:
            db.close()

    def _query(self, sql, params=()):
        if not self.config.enabled:
            return []
        with self._connection() as db:
            return [dict(row) for row in db.execute(sql, params).fetchall()]

    def _execute(self, sql, params=()):
        with self._write_lock, self._connection() as db:
            return db.execute(sql, params).rowcount

    def _get_meta(self, key):
        rows = self._query("SELECT value FROM history_meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    def _set_meta(self, key, value):
        self._execute("INSERT OR REPLACE INTO history_meta(key,value) VALUES(?,?)", (key, value))

    def close(self):
        self._closed = True

    def start_segment(self, segment_id, relpath, started_at, **metadata):
        validate_history_id(segment_id)
        safe_managed_path(self.config, relpath)
        if not relpath.startswith(("recordings/", "tmp/")):
            raise ValueError("recordings require a recordings or tmp media path")
        self._execute("INSERT INTO recordings(id,relpath,started_at,state,metadata) VALUES(?,?,?,'recording',?)",
                      (segment_id, relpath, _timestamp(started_at), _json(metadata)))
        return segment_id

    def finish_segment(self, segment_id, ended_at, size_bytes, **metadata):
        with self._write_lock:
            row = self.get_recording(segment_id)
            if row is None or row["state"] != "recording":
                raise ValueError("only a recording segment can complete")
            ended_at = _timestamp(ended_at)
            if ended_at < row["started_at"] or type(size_bytes) is not int or size_bytes < 0:
                raise ValueError("invalid completed segment interval or size")
            relpath = metadata.pop("relpath", row["relpath"])
            if not relpath.startswith("recordings/"):
                raise ValueError("completed segment must be in recordings")
            path = safe_managed_path(self.config, relpath, must_exist=True)
            if path.stat().st_size != size_bytes:
                raise ValueError("completed media size does not match file")
            merged = dict(row["metadata"])
            merged.update(metadata)
            self._execute("UPDATE recordings SET relpath=?,ended_at=?,size_bytes=?,metadata=?,state='complete',error=NULL WHERE id=?",
                          (relpath, ended_at, size_bytes, _json(merged), segment_id))

    def fail_segment(self, segment_id, error):
        self._execute("UPDATE recordings SET state='failed',error=? WHERE id=? AND state='recording'",
                      (str(error)[:1000], segment_id))

    def add_event(self, kind, started_at, person_id=None, payload=None, **kwargs):
        validate_event_kind(kind)
        started_at = _timestamp(started_at)
        ended_at = _timestamp(kwargs.pop("ended_at", None), optional=True)
        if ended_at is not None and ended_at < started_at:
            raise ValueError("event ends before it starts")
        event_id = kwargs.pop("event_id", uuid.uuid4().hex)
        validate_history_id(event_id)
        self._execute("INSERT INTO events(id,kind,started_at,ended_at,person_id,payload,metadata) VALUES(?,?,?,?,?,?,?)",
                      (event_id, kind, started_at, ended_at,
                       None if person_id is None else str(person_id), _json(payload), _json(kwargs)))
        return event_id

    def finish_event(self, event_id, ended_at):
        ended_at = _timestamp(ended_at)
        row = self.get_event(event_id)
        if row is None or ended_at < row["started_at"]:
            raise ValueError("invalid event completion")
        self._execute("UPDATE events SET ended_at=? WHERE id=?", (ended_at, event_id))

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        for name in ("metadata", "payload"):
            if name in row:
                row[name] = json.loads(row[name])
        return row

    def _list(self, table, start, end, limit, offset, kind=None):
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or offset < 0:
            raise ValueError("invalid pagination")
        start, end = _timestamp(start, True), _timestamp(end, True)
        if start is not None and end is not None and start >= end:
            raise ValueError("query start must precede end")
        clauses, params = [], []
        if start is not None:
            clauses.append("(ended_at IS NULL OR ended_at > ?)")
            params.append(start)
        if end is not None:
            clauses.append("started_at < ?")
            params.append(end)
        if kind is not None:
            clauses.append("kind=?")
            params.append(kind)
        sql = "SELECT * FROM " + table
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY started_at DESC,id LIMIT ? OFFSET ?"
        params.extend((limit, offset))
        return [self._decode(row) for row in self._query(sql, tuple(params))]

    def list_recordings(self, start=None, end=None, limit=50, offset=0):
        return self._list("recordings", start, end, limit, offset)

    def list_events(self, start=None, end=None, limit=50, offset=0, kind=None, event_type=None):
        selected_kind = kind if kind is not None else event_type
        if selected_kind is not None:
            validate_event_kind(selected_kind)
        return self._list("events", start, end, limit, offset, selected_kind)

    def list_gaps(self, start=None, end=None, limit=50, offset=0):
        return self._list("gaps", start, end, limit, offset)

    def get_recording(self, recording_id):
        rows = self._query("SELECT * FROM recordings WHERE id=?", (recording_id,))
        return self._decode(rows[0]) if rows else None

    def get_event(self, event_id):
        rows = self._query("SELECT * FROM events WHERE id=?", (event_id,))
        return self._decode(rows[0]) if rows else None

    def add_gap(self, started_at, ended_at, reason):
        start, end = _timestamp(started_at), _timestamp(ended_at, True)
        if end is not None and end < start:
            raise ValueError("gap ends before it starts")
        gap_id = uuid.uuid4().hex
        self._execute("INSERT INTO gaps(id,started_at,ended_at,reason) VALUES(?,?,?,?)",
                      (gap_id, start, end, str(reason)[:1000]))
        return gap_id

    def managed_size_bytes(self):
        return managed_usage(self.config) if self.config.enabled else 0

    def link_event_recording(self, event_id, recording_id, created_at=None):
        """Associate an event with a clip; repeated links are idempotent."""
        validate_history_id(event_id)
        validate_history_id(recording_id)
        created = _timestamp(created_at if created_at is not None else time.time())
        self._execute(
            "INSERT OR IGNORE INTO event_recordings(event_id,recording_id,created_at) VALUES(?,?,?)",
            (event_id, recording_id, created))
        return True

    def list_event_recordings(self, event_id):
        validate_history_id(event_id)
        rows = self._query(
            "SELECT r.* FROM recordings r JOIN event_recordings er ON er.recording_id=r.id "
            "WHERE er.event_id=? ORDER BY r.started_at, r.id", (event_id,))
        return [self._decode(row) for row in rows]

    def list_recording_events(self, recording_id):
        validate_history_id(recording_id)
        rows = self._query(
            "SELECT e.* FROM events e JOIN event_recordings er ON er.event_id=e.id "
            "WHERE er.recording_id=? ORDER BY e.started_at, e.id", (recording_id,))
        return [self._decode(row) for row in rows]
