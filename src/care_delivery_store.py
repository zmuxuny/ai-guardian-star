"""Scoped, transactional runtime state and at-least-once delivery outbox."""
import json
if __package__:
    from .local_care_store import LocalCareStore, _payload, _timestamp
    from .local_care_migrations import connection
else:
    from local_care_store import LocalCareStore, _payload, _timestamp
    from local_care_migrations import connection


class DeliveryStore(LocalCareStore):
    def _refresh_sample(self, db, event):
        # Hook participates in the SAME transaction as feedback and audit.
        pass

    def event(self, event_id, mode):
        with connection(self._path) as db:
            row = db.execute('SELECT * FROM care_events WHERE person_id=? AND model_version=? AND event_id=? AND mode=?',
                             self._params + (event_id, mode)).fetchone()
            return dict(row) if row else None

    def events(self, mode):
        with connection(self._path) as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM care_events WHERE person_id=? AND model_version=? AND mode=? ORDER BY started_at,event_id',
                self._params + (mode,))]

    def feedback_for_mode(self, mode, status='active'):
        if status not in ('active','revoked','all'):
            raise ValueError('invalid feedback status')
        if __package__:
            from .local_care_store import _feedback
        else:
            from local_care_store import _feedback
        suffix = '' if status == 'all' else ' AND f.is_revoked=' + ('1' if status == 'revoked' else '0')
        with connection(self._path) as db:
            return [_feedback(row) for row in db.execute('''SELECT f.* FROM feedback f JOIN care_events e
                ON e.person_id=f.person_id AND e.model_version=f.model_version AND e.event_id=f.target_id
                WHERE f.person_id=? AND f.model_version=? AND e.mode=?''' + suffix + ' ORDER BY f.updated_at,f.target_id',
                self._params + (mode,))]

    def session(self, mode):
        with connection(self._path) as db:
            row = db.execute('SELECT * FROM care_sessions WHERE person_id=? AND model_version=? AND mode=?',
                             self._params + (mode,)).fetchone()
            if not row:
                return None
            return {'checkpoint': json.loads(row['checkpoint_json']), 'active_event_id': row['active_event_id']}

    def _insert_event(self, db, ref):
        db.execute('INSERT OR IGNORE INTO care_events VALUES (?,?,?,?,?,?,?,?)',
                   self._params + tuple(ref[key] for key in ('event_id','mode','kind','region_id','started_at','ended_at')))

    def _enqueue(self, db, event_id, message_type, revision, payload, now):
        message_id = f'{event_id}:{message_type}:{revision}'
        db.execute('''INSERT OR IGNORE INTO care_outbox
            (person_id,model_version,message_id,mode,event_id,message_type,revision,payload_json,created_at)
            VALUES (?,?,?,'live',?,?,?,?,?)''',
                   self._params + (message_id, event_id, message_type, revision, _payload(payload), now))

    def save_step(self, mode, checkpoint, active_id, *, event=None, closed_id=None, messages=(), closed_at=None):
        now = _timestamp(self._clock())
        with self._write() as db:
            if event:
                self._insert_event(db, event)
            if closed_id:
                db.execute('UPDATE care_events SET ended_at=? WHERE person_id=? AND model_version=? AND event_id=? AND mode=? AND ended_at IS NULL',
                           (now if closed_at is None else closed_at,) + self._params + (closed_id, mode))
            for message in messages:
                if mode == 'live':
                    self._enqueue(db, message['event_id'], 'reminder', message['revision'], message, now)
            db.execute('''INSERT INTO care_sessions VALUES (?,?,?,?,?,?)
                ON CONFLICT(person_id,model_version,mode) DO UPDATE SET
                checkpoint_json=excluded.checkpoint_json,active_event_id=excluded.active_event_id,updated_at=excluded.updated_at''',
                       self._params + (mode, json.dumps(checkpoint, allow_nan=False), active_id, now))

    def create_event(self, ref):
        with self._write() as db:
            self._insert_event(db, ref)

    def event_feedback(self, event_id, mode, payload=None, *, operation='submit', reason=''):
        if operation not in ('submit','revoke','restore'):
            raise ValueError('invalid feedback operation')
        if not isinstance(reason, str) or len(reason) > 2000:
            raise ValueError('invalid revocation reason')
        now = _timestamp(self._clock())
        encoded = _payload(payload) if operation == 'submit' else None
        with self._write() as db:
            event = db.execute('SELECT * FROM care_events WHERE person_id=? AND model_version=? AND event_id=? AND mode=?',
                               self._params + (event_id, mode)).fetchone()
            if event is None:
                raise LookupError('event not found in person/model/mode scope')
            key = self._feedback_key(event_id, event['started_at'])
            if operation == 'submit':
                feedback = self._submit_in(db, key, event['started_at'], encoded, now)
            else:
                feedback = self._lifecycle_in(db, key, now, operation == 'revoke', reason if operation == 'revoke' else None)
            self._refresh_sample(db, event)
            if mode == 'live':
                self._enqueue(db, event_id, 'feedback', feedback['revision'],
                              {'schema_version': 1, 'event_id': event_id, 'feedback': feedback}, now)
            return feedback

    def pending(self, limit=100):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('invalid outbox limit')
        with connection(self._path) as db:
            result = []
            for row in db.execute('''SELECT * FROM care_outbox WHERE person_id=? AND model_version=?
                AND delivered_at IS NULL ORDER BY created_at,event_id,message_type,revision LIMIT ?''', self._params + (limit,)):
                record = dict(row)
                record['payload'] = json.loads(record.pop('payload_json'))
                result.append(record)
            return result

    def ack(self, message_id, *, delivered, error=None):
        with self._write() as db:
            db.execute('''UPDATE care_outbox SET attempts=attempts+1,last_error=?,delivered_at=?
                WHERE person_id=? AND model_version=? AND message_id=? AND delivered_at IS NULL''',
                       (error, _timestamp(self._clock()) if delivered else None) + self._params + (message_id,))
