"""Private event posture and feedback-derived samples, never sent by the outbox."""
import json
from datetime import datetime, timedelta, timezone

if __package__:
    from .weekly_store import WeeklyStore, mode_key
    from .local_care_store import _key, _timestamp, _payload
    from .local_care_migrations import connection
    from .posture_features import VERSION, CONFIG_VERSION, GUARDS, validate_feature, eligible_label, evaluate, histogram_bins
else:
    from weekly_store import WeeklyStore, mode_key
    from local_care_store import _key, _timestamp, _payload
    from local_care_migrations import connection
    from posture_features import VERSION, CONFIG_VERSION, GUARDS, validate_feature, eligible_label, evaluate, histogram_bins

LOCAL_TIME = timezone(timedelta(hours=8))
INVALID_REASONS = frozenset(('invalid_pose','invalid_or_truncated_box','unreliable_keypoints','degenerate_torso','ambiguous_identity'))


def refresh_sample(store, db, event):
    """Also used when collection is switched off: withdrawals still take effect."""
    keys = store._params+(event['mode'],event['event_id'])
    db.execute('DELETE FROM posture_samples WHERE person_id=? AND model_version=? AND mode=? AND event_id=?',keys)
    feature = db.execute('SELECT * FROM posture_features WHERE person_id=? AND model_version=? AND mode=? AND event_id=?',keys).fetchone()
    if feature is None or not feature['camera_revision'] or event['kind']!='fall':
        return
    if json.loads(feature['feature_json']).get('valid') is not True:
        return
    feedback = store._select_feedback(db,store._feedback_key(event['event_id'],event['started_at']),status='all')
    if feedback is None:
        return
    label = eligible_label(json.loads(feedback['payload_json']),bool(feedback['is_revoked']))
    if label:
        db.execute('INSERT INTO posture_samples VALUES (?,?,?,?,?,?)',keys+(label,feedback['revision']))


class PersonalBaselineStore(WeeklyStore):
    def _collecting(self, db):
        if db.execute('SELECT 1 FROM care_privacy WHERE person_id=? AND model_version=?',self._params).fetchone():
            raise ValueError('personal collection suspended')

    def capture_event(self, mode, event_id, feature, camera_revision, *, guards=None):
        mode_key(mode); _key(event_id,'event_id')
        camera = '' if camera_revision is None else _key(camera_revision,'camera_revision')
        if feature.get('valid') is True:
            validate_feature(feature)
        elif (set(feature)!={'version','valid','reason'} or feature.get('version')!=VERSION
              or feature.get('valid') is not False or feature.get('reason') not in INVALID_REASONS):
            raise ValueError('invalid rejection record')
        # Missing, unavailable and malformed guard values remain unknown.
        guards = guards if isinstance(guards,dict) else {}
        clean_guards = {k: guards[k] if type(guards.get(k)) is bool else
                        guards[k] if guards.get(k) in ('unknown','not_available') else None for k in GUARDS}
        encoded, guard_json = _payload(feature), _payload(clean_guards)
        with self._write() as db:
            self._collecting(db)
            event = db.execute('SELECT * FROM care_events WHERE person_id=? AND model_version=? AND mode=? AND event_id=?',
                               self._params+(mode,event_id)).fetchone()
            if event is None:
                raise LookupError('event absent in scope')
            old = db.execute('SELECT * FROM posture_features WHERE person_id=? AND model_version=? AND mode=? AND event_id=?',
                             self._params+(mode,event_id)).fetchone()
            values = self._params+(mode,event_id,VERSION,camera,encoded,guard_json,event['started_at'])
            if old and tuple(old)!=values:
                raise ValueError('event posture snapshot is immutable')
            db.execute('INSERT OR IGNORE INTO posture_features VALUES (?,?,?,?,?,?,?,?,?)',values)
            self._refresh_sample(db,event)

    def _refresh_sample(self, db, event):
        refresh_sample(self,db,event)

    def _samples_in(self, db, mode, camera):
        cutoff = self._clock()-self._policy_in(db,mode)['retention_days']*86400
        rows = db.execute('''SELECT s.event_id,s.label,f.feature_json FROM posture_samples s JOIN posture_features f
            ON s.person_id=f.person_id AND s.model_version=f.model_version AND s.mode=f.mode AND s.event_id=f.event_id
            WHERE s.person_id=? AND s.model_version=? AND s.mode=? AND f.camera_revision=? AND f.feature_version=?
            AND f.captured_at>=? ORDER BY f.captured_at DESC,s.event_id LIMIT 257''',
            self._params+(mode,camera,VERSION,cutoff)).fetchall()
        result = {'normal':[],'risk':[]}
        # If capped, do not discard a risk sample and accidentally relax a decision.
        if len(rows)>256:
            return result, True
        for row in rows:
            result[row['label']].append(dict(event_id=row['event_id'],feature=json.loads(row['feature_json'])))
        return result,False

    def samples(self, mode, camera_revision):
        mode_key(mode); _key(camera_revision,'camera_revision')
        with connection(self._path) as db:
            return self._samples_in(db,mode,camera_revision)[0]

    def observe_histogram(self, mode, feature, camera_revision, at):
        mode_key(mode); validate_feature(feature); _key(camera_revision,'camera_revision'); _timestamp(at)
        bins = histogram_bins(feature)
        day = datetime.fromtimestamp(at,LOCAL_TIME).replace(hour=0,minute=0,second=0,microsecond=0).timestamp()
        with self._write() as db:
            self._collecting(db)
            for axis,bin_index in bins.items():
                keys = self._params+(mode,VERSION,camera_revision,day,feature['region_id'],feature['time_slot'],axis,bin_index)
                db.execute('''INSERT INTO posture_histograms VALUES (?,?,?,?,?,?,?,?,?,?,1)
                    ON CONFLICT(person_id,model_version,mode,feature_version,camera_revision,day_start,region_id,time_slot,axis,bin)
                    DO UPDATE SET count=MIN(1000000000,count+1)''',keys)

    def personal_report(self, mode, camera_revision):
        mode_key(mode)
        camera = '' if camera_revision is None else _key(camera_revision,'camera_revision')
        with connection(self._path) as db:
            db.execute('BEGIN')
            cutoff = self._clock()-self._policy_in(db,mode)['retention_days']*86400
            rows = db.execute('''SELECT f.* FROM posture_features f JOIN care_events e
                ON f.person_id=e.person_id AND f.model_version=e.model_version AND f.event_id=e.event_id
                WHERE f.person_id=? AND f.model_version=? AND f.mode=? AND f.camera_revision=? AND f.feature_version=?
                AND f.captured_at>=? AND e.kind='fall' ORDER BY f.captured_at DESC,f.event_id LIMIT 1001''',
                self._params+(mode,camera,VERSION,cutoff)).fetchall()
            samples,capped = self._samples_in(db,mode,camera)
            hist = db.execute('''SELECT COALESCE(sum(count),0) FROM posture_histograms WHERE person_id=? AND model_version=?
                AND mode=? AND camera_revision=? AND feature_version=? AND day_start>=? AND axis='torso_angle' ''',
                self._params+(mode,camera,VERSION,cutoff)).fetchone()[0]
            db.execute('COMMIT')
        counts = dict(evaluated_events=0,normal_match_events=0,protected_events=0,insufficient_events=0,
                      would_extend_confirmation_events=0,positive_match_events=0,no_match_events=0,invalid_events=0)
        quality_reasons,protection_reasons={},{}
        for row in rows[:1000]:
            counts['evaluated_events']+=1
            feature = json.loads(row['feature_json'])
            if not feature.get('valid'):
                counts['invalid_events']+=1
                reason=feature['reason']
                quality_reasons[reason]=quality_reasons.get(reason,0)+1
                continue
            normal = [r for r in samples['normal'] if r['event_id']!=row['event_id']]
            risk = samples['risk']
            guards = json.loads(row['guards_json'])
            for name in GUARDS:
                value=guards.get(name)
                if value is not False:
                    reason=name+('_active' if value is True else '_not_available' if value=='not_available' else '_unknown')
                    protection_reasons[reason]=protection_reasons.get(reason,0)+1
            outcome = 'insufficient' if capped or not camera else evaluate(feature,normal,risk,guards)
            if outcome=='suggest_extend':
                counts['would_extend_confirmation_events']+=1
                counts['normal_match_events']+=1
            else:
                counts[{'protected':'protected_events','insufficient':'insufficient_events',
                        'positive_match':'positive_match_events','no_match':'no_match_events'}[outcome]]+=1
        return dict(schema_version=1,feature_version=VERSION,config_version=CONFIG_VERSION,
                    mode=mode,camera_revision=camera_revision,assessment='confirmed_event_static_suggestion',
                    histogram_observations=hist,normal_samples=len(samples['normal']),risk_samples=len(samples['risk']),
                    quality_reasons=quality_reasons,protection_reasons=protection_reasons,
                    truncated=len(rows)>1000,samples_capped=capped,**counts)
