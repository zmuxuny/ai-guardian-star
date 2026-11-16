"""Local SQLite feedback and personal baseline samples, scoped per person/model.

No network, sensors or audio imports. All mutations and their audit records share
one transaction. See docs/superpowers/specs/2026-11-16-local-care-storage.md.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import time

if __package__:
    from .local_care_migrations import connection, database_path, migrate_database
else:
    from local_care_migrations import connection, database_path, migrate_database


CATEGORIES = frozenset(('posture', 'activity', 'routine'))
WINDOW_SECONDS = 300


def _key(value, name):
    if (not isinstance(value, str) or not value or value != value.strip() or len(value) > 128
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError(f'{name} must be a nonempty identifier, at most 128 characters')
    return value


def _timestamp(value):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not 0 <= value <= 253402300799):
        raise ValueError('time must be finite nonnegative UTC Unix seconds, before year 10000')
    return float(value)


def _payload(value):
    if not isinstance(value, dict):
        raise ValueError('payload must be a JSON object')
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
        size = len(encoded.encode('utf-8'))
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise ValueError('payload must be finite, valid UTF-8 JSON') from exc
    if size > 65536:
        raise ValueError('payload exceeds 64 KiB')
    return encoded


def _category(value):
    if not isinstance(value, str) or value not in CATEGORIES:
        raise ValueError('category must be posture, activity or routine')
    return value


def _status(value, prefix=''):
    if value == 'active':
        return f' AND {prefix}is_revoked=0'
    if value == 'revoked':
        return f' AND {prefix}is_revoked=1'
    if value == 'all':
        return ''
    raise ValueError('status must be active, revoked or all')


def _feedback(row):
    if row is None:
        return None
    result = dict(row)
    result['payload'] = json.loads(result.pop('payload_json'))
    result['is_revoked'] = bool(result['is_revoked'])
    return result


@dataclass(frozen=True)
class Scope:
    person_id: str
    model_version: str

    def __post_init__(self):
        _key(self.person_id, 'person_id')
        _key(self.model_version, 'model_version')


class LocalCareStore:
    """Bind one immutable Scope; switching person/model requires another instance.

    File-based only. Clock returns UTC Unix seconds and is injectable for tests.
    IDs identify records within this scope, never across the entire device.
    """

    def __init__(self, path, person_id, model_version, *, clock=None):
        self._scope = Scope(person_id, model_version)
        self._clock = time.time if clock is None else clock
        if not callable(self._clock):
            raise ValueError('clock must be callable')
        self._path = database_path(path)
        self.migration = migrate_database(self._path)

    @property
    def scope(self):
        return self._scope

    @property
    def _params(self):
        return self.scope.person_id, self.scope.model_version

    def _feedback_key(self, target_id, event_at):
        event_at = _timestamp(event_at)
        return _key(target_id, 'target_id'), math.floor(event_at / WINDOW_SECONDS) * WINDOW_SECONDS

    @contextmanager
    def _write(self):
        with connection(self._path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise

    def _select_feedback(self, db, key, status='active'):
        return db.execute('SELECT * FROM feedback WHERE person_id=? AND model_version=? '
                          'AND target_id=? AND window_start=?' + _status(status),
                          self._params + key).fetchone()

    def _audit(self, db, row, operation):
        record = _feedback(row)
        db.execute('INSERT INTO feedback_audit '
                   '(person_id,model_version,target_id,window_start,revision,operation,recorded_at,snapshot_json) '
                   'VALUES (?,?,?,?,?,?,?,?)',
                   self._params + (record['target_id'], record['window_start'], record['revision'],
                                   operation, record['updated_at'],
                                   json.dumps(record, ensure_ascii=False, allow_nan=False)))

    def submit_feedback(self, target_id, event_at, payload):
        key = self._feedback_key(target_id, event_at)
        encoded, now = _payload(payload), _timestamp(self._clock())
        with self._write() as db:
            return self._submit_in(db, key, event_at, encoded, now)

    def _submit_in(self, db, key, event_at, encoded, now):
        """Shared transaction primitive, including audit, for durable delivery."""
        db.execute('''INSERT INTO feedback
                (person_id,model_version,target_id,window_start,event_at,payload_json,
                 created_at,updated_at,is_revoked,revision)
                VALUES (?,?,?,?,?,?,?,?,0,1)
                ON CONFLICT(person_id,model_version,target_id,window_start) DO UPDATE SET
                    payload_json=excluded.payload_json,
                    updated_at=MAX(feedback.updated_at,excluded.updated_at),
                    revision=feedback.revision+1''',
                       self._params + key + (float(event_at), encoded, now, now))
        row = self._select_feedback(db, key, status='all')
        self._audit(db, row, 'submit')
        return _feedback(row)

    def get_feedback(self, target_id, event_at, *, status='active'):
        key = self._feedback_key(target_id, event_at)
        _status(status)
        with connection(self._path) as db:
            return _feedback(self._select_feedback(db, key, status))

    def list_feedback(self, *, status='active', target_id=None):
        sql = 'SELECT * FROM feedback WHERE person_id=? AND model_version=?' + _status(status)
        params = self._params
        if target_id is not None:
            sql += ' AND target_id=?'
            params += (_key(target_id, 'target_id'),)
        sql += ' ORDER BY updated_at DESC,target_id,window_start'
        with connection(self._path) as db:
            return [_feedback(row) for row in db.execute(sql, params)]

    def count_feedback(self, *, status='active'):
        sql = 'SELECT count(*) FROM feedback WHERE person_id=? AND model_version=?' + _status(status)
        with connection(self._path) as db:
            return db.execute(sql, self._params).fetchone()[0]

    def _lifecycle(self, target_id, event_at, revoke, reason=None):
        key = self._feedback_key(target_id, event_at)
        now = _timestamp(self._clock())
        with self._write() as db:
            return self._lifecycle_in(db, key, now, revoke, reason)

    def _lifecycle_in(self, db, key, now, revoke, reason):
        row = self._select_feedback(db, key, status='all')
        if row is None:
            raise LookupError('feedback does not exist in this person/model scope')
        if bool(row['is_revoked']) == revoke:
            return _feedback(row)
        updated = max(now, row['updated_at'])
        db.execute('''UPDATE feedback SET is_revoked=?,revoked_at=?,revocation_reason=?,
                updated_at=?,revision=revision+1
                WHERE person_id=? AND model_version=? AND target_id=? AND window_start=?''',
                       (int(revoke), updated if revoke else None, reason, updated) + self._params + key)
        row = self._select_feedback(db, key, status='all')
        self._audit(db, row, 'revoke' if revoke else 'restore')
        return _feedback(row)

    def revoke_feedback(self, target_id, event_at, *, reason=''):
        if not isinstance(reason, str) or len(reason) > 2000:
            raise ValueError('revocation reason must be text, at most 2000 characters')
        return self._lifecycle(target_id, event_at, True, reason)

    def restore_feedback(self, target_id, event_at):
        return self._lifecycle(target_id, event_at, False)

    def feedback_audit(self, target_id, event_at, *, status):
        """Explicit status selects current feedback state, then its full history."""
        key = self._feedback_key(target_id, event_at)
        sql = '''SELECT a.* FROM feedback_audit a JOIN feedback f
            ON f.person_id=a.person_id AND f.model_version=a.model_version
                AND f.target_id=a.target_id AND f.window_start=a.window_start
            WHERE a.person_id=? AND a.model_version=? AND a.target_id=? AND a.window_start=?'''
        sql += _status(status, prefix='f.') + ' ORDER BY a.revision'
        with connection(self._path) as db:
            result = []
            for row in db.execute(sql, self._params + key):
                record = dict(row)
                record['snapshot'] = json.loads(record.pop('snapshot_json'))
                result.append(record)
            return result

    def put_sample(self, sample_id, category, payload, *, sampled_at, source=None):
        sample_id, category = _key(sample_id, 'sample_id'), _category(category)
        encoded, sampled_at = _payload(payload), _timestamp(sampled_at)
        now = _timestamp(self._clock())
        if source is not None and (not isinstance(source, str) or len(source) > 1000):
            raise ValueError('source must be text, at most 1000 characters, or None')
        with self._write() as db:
            db.execute('''INSERT INTO baseline_samples
                (person_id,model_version,sample_id,category,payload_json,sampled_at,created_at,updated_at,source)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(person_id,model_version,sample_id) DO UPDATE SET
                    category=excluded.category,payload_json=excluded.payload_json,
                    sampled_at=excluded.sampled_at,source=excluded.source,
                    updated_at=MAX(baseline_samples.updated_at,excluded.updated_at)''',
                       self._params + (sample_id, category, encoded, sampled_at, now, now, source))
            row = db.execute('SELECT * FROM baseline_samples WHERE person_id=? AND model_version=? AND sample_id=?',
                             self._params + (sample_id,)).fetchone()
            return self._sample(row)

    @staticmethod
    def _sample(row):
        if row is None:
            return None
        result = dict(row)
        result['payload'] = json.loads(result.pop('payload_json'))
        return result

    def get_sample(self, sample_id):
        sample_id = _key(sample_id, 'sample_id')
        with connection(self._path) as db:
            return self._sample(db.execute(
                'SELECT * FROM baseline_samples WHERE person_id=? AND model_version=? AND sample_id=?',
                self._params + (sample_id,)).fetchone())

    def list_samples(self, *, category=None):
        sql = 'SELECT * FROM baseline_samples WHERE person_id=? AND model_version=?'
        params = self._params
        if category is not None:
            sql += ' AND category=?'
            params += (_category(category),)
        with connection(self._path) as db:
            return [self._sample(row) for row in db.execute(sql + ' ORDER BY sampled_at,sample_id', params)]
