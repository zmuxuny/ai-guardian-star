"""Isolated v5 wire contract and durable test-device delivery; no care writes."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import math

from .local_care_migrations import connection, database_path

APP_ID = 0x56355458
RESPONSES = frozenset(('ok', 'needs_help', 'unclear', 'no_response'))
ERRORS = frozenset(('input_unavailable', 'prompt_failed', 'session_timeout',
                    'expired_before_prompt', 'interrupted'))
EVENT_EXTRA = 86400 + 90 + 300 + 5


class ProtocolError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def iso(seconds):
    return datetime.fromtimestamp(seconds, timezone.utc).isoformat()


def instant(value):
    if not isinstance(value, str) or len(value) > 100:
        raise ProtocolError(400, 'invalid timestamp')
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.utcoffset() is None:
            raise ValueError('timezone required')
        return parsed.timestamp()
    except (ValueError, OverflowError) as error:
        raise ProtocolError(400, 'timestamp requires ISO8601 timezone') from error


def string(value, name, limit=2000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c)<32 for c in value):
        raise ProtocolError(400, 'invalid '+name)
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise ProtocolError(400, 'invalid UTF8') from error
    return value


def validate(payload, kind, device):
    if not isinstance(payload, dict):
        raise ProtocolError(400, 'JSON object required')
    if 'schema_version' not in payload:
        raise ProtocolError(400, 'schema_version required')
    if payload['schema_version'] != '2':
        raise ProtocolError(422, 'unsupported schema_version')
    out = {'schema_version': '2', 'event_id': string(payload.get('event_id'), 'event_id', 128)}
    if 'device_id' in payload:
        out['device_id'] = string(payload['device_id'], 'device_id', 128)
        if out['device_id'] != device:
            raise ProtocolError(400, 'device mismatch')
    out['timestamp'] = iso(instant(payload.get('timestamp')))
    if kind == 'reminder':
        for key in ('alert_type', 'reason'):
            out[key] = string(payload.get(key), key)
        out['expires_at'] = iso(instant(payload.get('expires_at')))
        if instant(out['expires_at']) <= instant(out['timestamp']):
            raise ProtocolError(400, 'expires_at must follow timestamp')
    elif kind == 'result':
        revision = payload.get('revision')
        if type(revision) is not int or not 1 <= revision <= 2147483647:
            raise ProtocolError(400, 'positive revision required')
        out.update(revision=revision, status=payload.get('status'))
        if (out['status'] == 'completed' and isinstance(payload.get('response'), str)
                and payload['response'] in RESPONSES and 'error_code' not in payload):
            out['response'] = payload['response']
        elif (out['status'] == 'error' and isinstance(payload.get('error_code'), str)
              and payload['error_code'] in ERRORS and 'response' not in payload):
            out['error_code'] = payload['error_code']
        else:
            raise ProtocolError(400, 'invalid status/response/error combination')
        if 'prompted_at' in payload:
            out['prompted_at'] = iso(instant(payload['prompted_at']))
    else:
        raise ValueError('invalid message kind')
    return out


def encoded(payload):
    return json.dumps(payload, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(',', ':'))


def receipt(payload, disposition):
    out = dict(schema_version='2', event_id=payload['event_id'], disposition=disposition)
    if 'revision' in payload:
        out['revision'] = payload['revision']
    return out


class Store:
    """One dedicated DB per role/device. No retention deletion in this release."""
    def __init__(self, path, device_id, role, *, clock=None):
        import time
        self.path = database_path(path)
        self.device = string(device_id, 'device_id', 128)
        if role not in ('model', 'peer'):
            raise ValueError('invalid role')
        self.role = role
        self.clock = clock or time.time
        with self.write() as db:
            app = db.execute('PRAGMA application_id').fetchone()[0]
            tables = {x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not tables and app == 0:
                for sql in (
                    'CREATE TABLE binding(device TEXT NOT NULL,role TEXT NOT NULL)',
                    '''CREATE TABLE events(event_id TEXT PRIMARY KEY, reminder TEXT NOT NULL,
                       saved_at REAL NOT NULL, state TEXT NOT NULL, slot INTEGER UNIQUE,
                       latest TEXT, first_result REAL, late_until REAL, help_required INTEGER NOT NULL DEFAULT 0)''',
                    '''CREATE TABLE results(event_id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,
                       PRIMARY KEY(event_id,revision),FOREIGN KEY(event_id) REFERENCES events(event_id))''',
                    '''CREATE TABLE outbox(id INTEGER PRIMARY KEY,event_id TEXT NOT NULL,kind TEXT NOT NULL,
                       revision INTEGER NOT NULL,payload TEXT NOT NULL,created REAL NOT NULL,deadline REAL NOT NULL,
                       next_due REAL NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'pending',
                       last_error TEXT,UNIQUE(event_id,kind,revision),FOREIGN KEY(event_id) REFERENCES events(event_id))''',
                    'CREATE TABLE help_tasks(event_id TEXT PRIMARY KEY,created REAL NOT NULL,FOREIGN KEY(event_id) REFERENCES events(event_id))'):
                    db.execute(sql)
                db.execute('INSERT INTO binding VALUES (?,?)', (self.device, role))
                db.execute('PRAGMA application_id='+str(APP_ID))
                db.execute('PRAGMA user_version=1')
            elif app != APP_ID or db.execute('PRAGMA user_version').fetchone()[0] != 1 or tables != {'binding','events','results','outbox','help_tasks'}:
                raise ValueError('refusing unknown database')
            if [tuple(x) for x in db.execute('SELECT * FROM binding')] != [(self.device, role)]:
                raise ValueError('database binding differs')

    @contextmanager
    def write(self):
        with connection(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.execute('COMMIT')
            except BaseException:
                if db.in_transaction:
                    db.execute('ROLLBACK')
                raise

    def _event(self, db, event_id):
        row = db.execute('SELECT * FROM events WHERE event_id=?', (event_id,)).fetchone()
        if row is None:
            raise ProtocolError(404, 'unknown event')
        out = dict(row)
        for key in ('reminder','state','latest'):
            out[key] = json.loads(out[key]) if out[key] is not None else None
        return out

    def event(self, event_id):
        with connection(self.path) as db:
            return self._event(db, event_id)

    def events(self):
        with connection(self.path) as db:
            return [self._event(db, r[0]) for r in db.execute('SELECT event_id FROM events ORDER BY saved_at,event_id')]

    def _new(self, db, payload, slot):
        now = self.clock()
        state = {'phase':'pending' if slot else 'registered', 'prompt_count':0, 'ever_input':False}
        db.execute('INSERT INTO events(event_id,reminder,saved_at,state,slot) VALUES (?,?,?,?,?)',
                   (payload['event_id'], encoded(payload), now, encoded(state), slot))

    def accept_reminder(self, payload, *, available=True):
        if self.role != 'model':
            raise ProtocolError(400, 'model role required')
        value = validate(payload, 'reminder', self.device)
        with self.write() as db:
            row = db.execute('SELECT reminder FROM events WHERE event_id=?', (value['event_id'],)).fetchone()
            if row:
                if row[0] != encoded(value):
                    raise ProtocolError(409, 'reminder conflict')
                return receipt(value, 'duplicate')
            if self.clock() >= instant(value['expires_at']):
                return receipt(value, 'expired')
            if not available or db.execute('SELECT 1 FROM events WHERE slot=1').fetchone():
                raise ProtocolError(503, 'active session busy')
            self._new(db, value, 1)
        return receipt(value, 'accepted')

    def register_reminder(self, payload):
        if self.role != 'peer':
            raise ProtocolError(400, 'peer role required')
        value = validate(payload, 'reminder', self.device)
        with self.write() as db:
            row = db.execute('SELECT reminder FROM events WHERE event_id=?', (value['event_id'],)).fetchone()
            if row:
                if row[0] != encoded(value):
                    raise ProtocolError(409, 'registered event conflict')
            else:
                self._new(db, value, None)
                self._enqueue(db, value, 'reminder', instant(value['expires_at']))
        return value

    def _enqueue(self, db, payload, kind, deadline):
        now = self.clock()
        db.execute('''INSERT INTO outbox(event_id,kind,revision,payload,created,deadline,next_due,state)
                      VALUES (?,?,?,?,?,?,?,?)''', (payload['event_id'], kind, payload.get('revision', 0),
                      encoded(payload), now, deadline, now, 'pending' if now < deadline else 'stopped'))

    def _save_result(self, db, event, *, response=None, error=None, received_at=None, prompted_at=None):
        if (response is None) == (error is None):
            raise ValueError('one response or error required')
        latest = event['latest']
        now = self.clock()
        if latest:
            if latest.get('response') == 'needs_help' or latest.get('response') == response:
                return latest
            if received_at is None or not received_at < event['late_until']:
                raise ProtocolError(410, 'late input requires independent help/manual route')
            if response not in ('ok','needs_help') or (latest.get('response') == 'ok' and response != 'needs_help'):
                return latest
        payload = dict(schema_version='2', event_id=event['event_id'], revision=latest['revision']+1 if latest else 1,
                       timestamp=iso(now), status='error' if error else 'completed')
        payload.update({'error_code':error} if error else {'response':response})
        if 'device_id' in event['reminder']:
            payload['device_id'] = event['reminder']['device_id']
        prompt = prompted_at or event['state'].get('prompted_at')
        if prompt is not None:
            payload['prompted_at'] = iso(prompt)
        payload = validate(payload, 'result', self.device)
        db.execute('INSERT INTO results VALUES (?,?,?)', (event['event_id'], payload['revision'], encoded(payload)))
        state = {**event['state'], 'phase':'finished'}
        db.execute('''UPDATE events SET latest=?,state=?,slot=NULL,first_result=COALESCE(first_result,?),
                      late_until=COALESCE(late_until,?),help_required=MAX(help_required,?) WHERE event_id=?''',
                   (encoded(payload), encoded(state), now, now+300, int(response=='needs_help'), event['event_id']))
        deadline = min(now+86400, instant(event['reminder']['expires_at'])+EVENT_EXTRA)
        self._enqueue(db, payload, 'result', deadline)
        return payload

    def complete(self, event_id, **kwargs):
        if self.role != 'model':
            raise ProtocolError(400, 'model role required')
        with self.write() as db:
            return self._save_result(db, self._event(db, event_id), **kwargs)

    def mutate(self, event_id, step):
        """Serialize state-machine changes and a possible result/outbox together."""
        with self.write() as db:
            event = self._event(db, event_id)
            result = step(event)
            db.execute('UPDATE events SET state=? WHERE event_id=?', (encoded(event['state']), event_id))
            if result is not None:
                return self._save_result(db, event, **result)
            return None

    def accept_result(self, payload):
        if self.role != 'peer':
            raise ProtocolError(400, 'peer role required')
        value = validate(payload, 'result', self.device)
        with self.write() as db:
            event = self._event(db, value['event_id'])
            if ('device_id' in value) != ('device_id' in event['reminder']):
                raise ProtocolError(400, 'result device presence must follow reminder')
            old = db.execute('SELECT payload FROM results WHERE event_id=? AND revision=?',
                             (value['event_id'], value['revision'])).fetchone()
            if old:
                if old[0] != encoded(value):
                    raise ProtocolError(409, 'result revision conflict')
                return receipt(value, 'duplicate')
            db.execute('INSERT INTO results VALUES (?,?,?)', (value['event_id'], value['revision'], encoded(value)))
            if event['latest'] is None or value['revision'] > event['latest']['revision']:
                db.execute('UPDATE events SET latest=? WHERE event_id=?', (encoded(value), value['event_id']))
            if value.get('response') == 'needs_help':
                db.execute('UPDATE events SET help_required=1 WHERE event_id=?', (value['event_id'],))
                db.execute('INSERT OR IGNORE INTO help_tasks VALUES (?,?)', (value['event_id'], self.clock()))
            db.execute("UPDATE outbox SET state='delivered' WHERE event_id=? AND kind='reminder'", (value['event_id'],))
        return receipt(value, 'accepted')

    def pending(self):
        now = self.clock()
        with self.write() as db:
            db.execute("UPDATE outbox SET state='stopped',last_error='deadline' WHERE state='pending' AND deadline<=?", (now,))
            return [self._delivery(row) for row in db.execute(
                "SELECT * FROM outbox WHERE state='pending' AND next_due<=? ORDER BY id", (now,))]

    @staticmethod
    def _delivery(row):
        out = dict(row)
        out['payload'] = json.loads(out['payload'])
        return out

    def failed_deliveries(self):
        self.pending()
        with connection(self.path) as db:
            return [self._delivery(r) for r in db.execute("SELECT * FROM outbox WHERE state='stopped' ORDER BY id")]

    def help_tasks(self):
        with connection(self.path) as db:
            return [dict(r) for r in db.execute('SELECT * FROM help_tasks ORDER BY event_id')]

    def record_delivery(self, item_id, http_status, ack):
        with self.write() as db:
            row = db.execute('SELECT * FROM outbox WHERE id=?', (item_id,)).fetchone()
            if row is None or row['state'] != 'pending':
                return
            payload = json.loads(row['payload'])
            dispositions = ('accepted','duplicate','expired') if row['kind']=='reminder' else ('accepted','duplicate')
            valid = (http_status == 200 and isinstance(ack, dict) and ack.get('schema_version')=='2'
                     and ack.get('event_id')==payload['event_id'] and ack.get('disposition') in dispositions
                     and (row['kind']=='reminder' or (type(ack.get('revision')) is int and ack['revision']==payload['revision'])))
            state = 'delivered' if valid else 'pending'
            error = None if valid else ('invalid_ack' if http_status==200 else 'http_'+str(http_status))
            if not valid and http_status in (400,404,409,422):
                state = 'stopped'
            if valid and ack['disposition']=='expired':
                state, error = 'stopped', 'expired_not_received'
            attempts = row['attempts']+1
            delay = (5,15,30)[min(attempts-1,2)] if attempts<=3 else (30 if row['kind']=='reminder' else 60)
            now = self.clock()
            if now >= row['deadline']:
                state, error = 'stopped', 'deadline'
            db.execute('UPDATE outbox SET state=?,attempts=?,last_error=?,next_due=? WHERE id=?',
                       (state,attempts,error,now+delay,item_id))
