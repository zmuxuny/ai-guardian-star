"""Scoped weekly sources and transactional lifecycle; no materialized statistics."""
import math
import uuid
if __package__:
    from .care_delivery_store import DeliveryStore
    from .local_care_store import _key, _timestamp
    from .local_care_migrations import connection
    from .weekly_report import aggregate, week_bounds
else:
    from care_delivery_store import DeliveryStore
    from local_care_store import _key, _timestamp
    from local_care_migrations import connection
    from weekly_report import aggregate, week_bounds


def mode_key(mode):
    if mode not in ('live','shadow'):
        raise ValueError('invalid mode')
    return mode


class WeeklyStore(DeliveryStore):
    def coverage(self, mode, region_id, start, end, *, valid, quality):
        """Runtime-only append. Coalesce adjacent equal spans, at most an hour.

        Source replay/idempotence imports should use observe() with stable IDs.
        """
        mode_key(mode)
        _key(region_id,'region_id')
        _timestamp(start); _timestamp(end)
        if end <= start or end-start > 30 or type(valid) is not bool:
            raise ValueError('invalid runtime coverage')
        if quality is not None and (type(quality) not in (int,float) or not math.isfinite(quality) or not 0 <= quality <= 1):
            raise ValueError('invalid quality')
        with self._write() as db:
            if db.execute('SELECT 1 FROM care_privacy WHERE person_id=? AND model_version=?',self._params).fetchone():
                return
            row = db.execute('''SELECT * FROM weekly_observations WHERE person_id=? AND model_version=? AND mode=?
                ORDER BY ended_at DESC LIMIT 1''',self._params+(mode,)).fetchone()
            if (row and row['ended_at']==start and row['region_id']==region_id and row['valid']==valid
                    and row['quality']==quality and end-row['started_at'] <= 3600):
                db.execute('UPDATE weekly_observations SET ended_at=? WHERE person_id=? AND model_version=? AND mode=? AND observation_id=?',
                           (end,)+self._params+(mode,row['observation_id']))
            else:
                db.execute('INSERT INTO weekly_observations VALUES (?,?,?,?,?,?,?,?,?)',
                           self._params+(mode,uuid.uuid4().hex,region_id,start,end,int(valid),quality))

    def erased(self):
        with connection(self._path) as db:
            return db.execute('SELECT 1 FROM care_privacy WHERE person_id=? AND model_version=?', self._params).fetchone() is not None

    def policy(self, mode):
        mode_key(mode)
        with connection(self._path) as db:
            return self._policy_in(db,mode)

    def _policy_in(self, db, mode):
        row = db.execute('SELECT retention_days,min_samples,last_cleanup FROM weekly_policies WHERE person_id=? AND model_version=? AND mode=?', self._params+(mode,)).fetchone()
        return dict(row) if row else dict(retention_days=90,min_samples=30,last_cleanup=None)

    def set_policy(self, mode, *, retention_days, min_samples):
        mode_key(mode)
        if type(retention_days) is not int or not 1 <= retention_days <= 3650 or type(min_samples) is not int or not 1 <= min_samples <= 10080:
            raise ValueError('invalid weekly policy')
        with self._write() as db:
            db.execute('''INSERT INTO weekly_policies VALUES (?,?,?,?,?,NULL)
                ON CONFLICT(person_id,model_version,mode) DO UPDATE SET
                retention_days=excluded.retention_days,min_samples=excluded.min_samples,last_cleanup=NULL''',
                self._params+(mode,retention_days,min_samples))
        return self.policy(mode)

    def observe(self, mode, observation_id, region_id, started_at, ended_at, *, valid=True, quality=None):
        mode_key(mode)
        _key(observation_id,'observation_id'); _key(region_id,'region_id')
        a,b = _timestamp(started_at),_timestamp(ended_at)
        if b <= a or b-a > 86400 or type(valid) is not bool:
            raise ValueError('invalid observation interval')
        if quality is not None and (type(quality) not in (int,float) or not math.isfinite(quality) or not 0 <= quality <= 1):
            raise ValueError('invalid observation quality')
        values = self._params+(mode,observation_id,region_id,a,b,int(valid),quality)
        with self._write() as db:
            if db.execute('SELECT 1 FROM care_privacy WHERE person_id=? AND model_version=?', self._params).fetchone():
                raise ValueError('personal data collection is suspended')
            old = db.execute('SELECT * FROM weekly_observations WHERE person_id=? AND model_version=? AND mode=? AND observation_id=?', self._params+(mode,observation_id)).fetchone()
            if old and tuple(old) != values:
                raise ValueError('observation identity conflict')
            db.execute('INSERT OR IGNORE INTO weekly_observations VALUES (?,?,?,?,?,?,?,?,?)', values)

    def weekly(self, mode, week_start, *, regions, offset_minutes=480, min_samples=None):
        mode_key(mode)
        if not isinstance(regions,(tuple,list)) or not 1 <= len(regions) <= 16 or len(set(regions))!=len(regions):
            raise ValueError('configure 1..16 coarse regions')
        for region in regions:
            _key(region,'region_id')
        start,end = week_bounds(week_start, offset_minutes)
        policy = self.policy(mode)
        threshold = policy['min_samples'] if min_samples is None else min_samples
        if type(threshold) is not int or not 1 <= threshold <= 10080:
            raise ValueError('invalid sample threshold')
        cutoff = max(0, _timestamp(self._clock())-policy['retention_days']*86400)
        # One read transaction: feedback revoke/cleanup cannot yield mixed snapshots.
        with connection(self._path) as db:
            db.execute('BEGIN')
            events = [dict(r) for r in db.execute('''SELECT * FROM care_events WHERE person_id=? AND model_version=? AND mode=?
                AND started_at>=? AND started_at<?''', self._params+(mode,max(cutoff,start-604800),end))]
            observations = [dict(r) for r in db.execute('''SELECT * FROM weekly_observations WHERE person_id=? AND model_version=? AND mode=?
                AND ended_at>? AND started_at<?''', self._params+(mode,max(cutoff,start-604800),end))]
            for o in observations:
                o['started_at'] = max(o['started_at'],cutoff)
            import json
            confirmations = set()
            for row in db.execute('''SELECT f.target_id,f.payload_json FROM feedback f JOIN care_events e
                ON e.person_id=f.person_id AND e.model_version=f.model_version AND e.event_id=f.target_id
                WHERE f.person_id=? AND f.model_version=? AND e.mode=? AND f.is_revoked=0''', self._params+(mode,)):
                payload = json.loads(row['payload_json'])
                if payload.get('confirmed') is True or payload.get('label')=='confirmed':
                    confirmations.add(row['target_id'])
            db.execute('COMMIT')
        # Unknown raw regions collapse to explicit unknown, never silently vanish.
        regions = tuple(regions)
        if any(r['region_id'] not in regions for r in events+observations) and 'unknown' not in regions:
            regions += ('unknown',)
        for row in events+observations:
            if row['region_id'] not in regions:
                row['region_id']='unknown'
        result = aggregate(week_start=week_start,offset_minutes=offset_minutes,regions=regions,
                           events=events,observations=observations,confirmations=confirmations,min_samples=threshold)
        result.update(person_id=self.scope.person_id,model_version=self.scope.model_version,mode=mode,
                      retention_cutoff=cutoff)
        return result

    def maintain(self, mode):
        """Called on detection/tick; hourly, no background network or wall sleeps.

        Clock must be locally provisioned (2020+); backwards jumps skip cleanup.
        Active checkpoint event is retained. Report reads independently clip TTL.
        """
        mode_key(mode)
        now = _timestamp(self._clock())
        policy = self.policy(mode)
        last = policy['last_cleanup']
        if now < 1577836800 or last is not None and now-last < 3600:
            return {'status':'clock_or_interval_skip','deleted_events':0}
        cutoff = now-policy['retention_days']*86400
        with self._write() as db:
            # Re-read under the writer lock: a concurrent policy extension
            # must never be followed by deletion using the previous short TTL.
            policy = self._policy_in(db,mode)
            last = policy['last_cleanup']
            if last is not None and now-last < 3600:
                return {'status':'clock_or_interval_skip','deleted_events':0}
            cutoff = now-policy['retention_days']*86400
            ids = [r[0] for r in db.execute('''SELECT event_id FROM care_events WHERE person_id=? AND model_version=? AND mode=?
                AND COALESCE(ended_at,started_at)<? AND event_id NOT IN
                (SELECT active_event_id FROM care_sessions WHERE person_id=? AND model_version=? AND mode=? AND active_event_id IS NOT NULL)''',
                self._params+(mode,cutoff)+self._params+(mode,))]
            for identity in ids:
                for table in ('posture_samples','posture_features'):
                    db.execute(f'DELETE FROM {table} WHERE person_id=? AND model_version=? AND mode=? AND event_id=?',
                               self._params+(mode,identity))
                for table in ('feedback_audit','feedback'):
                    db.execute(f'DELETE FROM {table} WHERE person_id=? AND model_version=? AND target_id=?', self._params+(identity,))
                db.execute('DELETE FROM care_outbox WHERE person_id=? AND model_version=? AND event_id=?',self._params+(identity,))
                db.execute('DELETE FROM care_events WHERE person_id=? AND model_version=? AND mode=? AND event_id=?',self._params+(mode,identity))
            db.execute('DELETE FROM weekly_observations WHERE person_id=? AND model_version=? AND mode=? AND ended_at<=?',self._params+(mode,cutoff))
            db.execute('DELETE FROM posture_histograms WHERE person_id=? AND model_version=? AND mode=? AND day_start<?',
                       self._params+(mode,cutoff))
            db.execute('UPDATE weekly_observations SET started_at=? WHERE person_id=? AND model_version=? AND mode=? AND started_at<? AND ended_at>?',
                       (cutoff,)+self._params+(mode,cutoff,cutoff))
            db.execute('''INSERT INTO weekly_policies VALUES (?,?,?,?,?,?) ON CONFLICT(person_id,model_version,mode)
                DO UPDATE SET last_cleanup=excluded.last_cleanup''',self._params+(mode,policy['retention_days'],policy['min_samples'],now))
        return {'status':'cleaned','deleted_events':len(ids)}

    def erase(self):
        with self._write() as db:
            for table in ('posture_samples','posture_features','posture_histograms','feedback_audit','feedback','baseline_samples','care_outbox','care_sessions','care_events','weekly_observations','weekly_policies'):
                db.execute(f'DELETE FROM {table} WHERE person_id=? AND model_version=?',self._params)
            db.execute('INSERT OR REPLACE INTO care_privacy VALUES (?,?,?)',self._params+(_timestamp(self._clock()),))
        return {'status':'erased'}

    def resume(self):
        with self._write() as db:
            db.execute('DELETE FROM care_privacy WHERE person_id=? AND model_version=?',self._params)
        return {'status':'resumed'}
