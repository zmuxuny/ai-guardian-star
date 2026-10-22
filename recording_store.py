"""Single-board 24-hour recording index. Times are UTC epoch milliseconds.

Video stays on the server, never in the account DB. Only finalized MP4s are indexed.
The broker records detection intervals even when no phone is running.
"""
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(os.environ.get('RECORDING_ROOT', '/var/lib/guardian-recordings'))
DAY = 86_400_000
PADDING = 60_000


@contextmanager
def connect():
    ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(ROOT / 'index.sqlite', timeout=5)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS segments (
        id TEXT PRIMARY KEY, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
        filename TEXT NOT NULL UNIQUE, size INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS segment_time ON segments(start_ms, end_ms);
      CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY, kind TEXT NOT NULL, start_ms INTEGER NOT NULL,
        end_ms INTEGER, last_seen_ms INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
    ''')
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def set_state(value):
    with connect() as db:
        db.execute('INSERT OR REPLACE INTO state VALUES (?, ?)',
                   ('recorder', json.dumps({'status': value, 'updatedAt': int(time.time() * 1000)})))


def ingest_alert(payload, now=None):
    """Called only for authenticated board alert messages; never persist raw payloads.

    Explicit normal/other states close an interval. A gap is marked unknown, not
    presented as a proven recovery. Repeated same-state messages extend the interval.
    """
    if len(payload) > 16384:
        return
    try:
        data = json.loads(payload)
        if not isinstance(data, dict):
            return
        value = str(data.get('event', data.get('alert_type', data.get('type', '')))).lower().strip()
    except (ValueError, TypeError, UnicodeError):
        return
    normal = any(word in value for word in ('no fall', 'normal', 'stand', 'walk'))
    if not normal and any(word in value for word in ('sedentary', '久坐', 'sitting_long', 'sit')):
        kind = 'sedentary'
    elif not normal and any(word in value for word in ('fall', '跌倒')):
        kind = 'fall'
    else:
        kind = ''
    now = int(time.time() * 1000) if now is None else now
    with connect() as db:
        previous = db.execute('SELECT * FROM events WHERE end_ms IS NULL ORDER BY id DESC LIMIT 1').fetchone()
        if previous and now - previous['last_seen_ms'] <= 30_000:
            if previous['kind'] == kind:
                db.execute('UPDATE events SET last_seen_ms=? WHERE id=?', (now, previous['id']))
                return
            db.execute('UPDATE events SET end_ms=? WHERE id=?', (now, previous['id']))
        if kind:
            db.execute('INSERT INTO events(kind,start_ms,last_seen_ms) VALUES(?,?,?)', (kind, now, now))


def snapshot(as_of, kind):
    now = int(time.time() * 1000)
    as_of = min(int(as_of), now)
    start = as_of - DAY
    available_start = max(start, now - DAY)
    with connect() as db:
        segments = db.execute('SELECT * FROM segments WHERE start_ms<? AND end_ms>? ORDER BY start_ms',
                              (as_of, available_start)).fetchall()
        events = db.execute('SELECT * FROM events WHERE start_ms<=? AND COALESCE(end_ms,last_seen_ms)>=? ORDER BY start_ms',
                            (as_of, available_start - PADDING)).fetchall()
        row = db.execute("SELECT value FROM state WHERE key='recorder'").fetchone()
    state = json.loads(row[0]) if row else {'status': 'waiting', 'updatedAt': 0}
    if now - state['updatedAt'] > 120_000:
        state['status'] = 'unavailable'
    windows = []
    if kind == 'all':
        windows = [(available_start, as_of, False)]
    else:
        for event in events:
            if event['kind'] != kind:
                continue
            ongoing = event['end_ms'] is None
            end = event['end_ms'] if not ongoing else (as_of if as_of - event['last_seen_ms'] <= 30_000 else event['last_seen_ms'])
            left, right = max(available_start, event['start_ms'] - PADDING), min(as_of, end + PADDING)
            if right <= left:
                continue
            if windows and left <= windows[-1][1]:
                windows[-1] = (windows[-1][0], max(right, windows[-1][1]), ongoing or windows[-1][2])
            else:
                windows.append((left, right, ongoing))
    clips = []
    for segment in segments:
        if not (ROOT / segment['filename']).is_file():
            continue
        for left, right, ongoing in windows:
            clip_start, clip_end = max(left, segment['start_ms']), min(right, segment['end_ms'])
            if clip_end > clip_start:
                clips.append({'id': f"{segment['id']}:{clip_start}:{clip_end}", 'segmentId': segment['id'],
                              'startTime': clip_start, 'endTime': clip_end, 'eventType': kind,
                              'endUnconfirmed': ongoing})
    return {'success': True, 'asOf': as_of, 'windowStart': start, 'windowEnd': as_of,
            'status': state['status'], 'clips': clips,
            'eventCount': sum(1 for event in events if kind == 'all' or event['kind'] == kind)}


def prune():
    """Delete expired owned files only. Keep the straddling segment for the boundary.

    MP4 access is clipped again at request time so the extra boundary bytes are
    never exposed as footage outside the authorized 24-hour window.
    """
    cutoff = int(time.time() * 1000) - DAY
    with connect() as db:
        rows = db.execute('SELECT id,filename FROM segments WHERE end_ms<=?', (cutoff,)).fetchall()
        for row in rows:
            path = ROOT / row['filename']
            if path.parent == ROOT and path.suffix == '.mp4':
                path.unlink(missing_ok=True)
            db.execute('DELETE FROM segments WHERE id=?', (row['id'],))
        db.execute('DELETE FROM events WHERE COALESCE(end_ms,last_seen_ms)<?', (cutoff - PADDING,))
    for path in ROOT.glob('clip-*.mp4'):
        if path.stat().st_mtime < time.time() - 900:
            path.unlink(missing_ok=True)
