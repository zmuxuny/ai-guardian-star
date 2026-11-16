"""Opt-in detection/state/feedback/shadow integration. No device/network imports."""
from dataclasses import dataclass, field, fields
from collections import deque
from copy import deepcopy
from datetime import datetime, timedelta, timezone, time as wall_time
import json
import os
from pathlib import Path
import threading
import time
import uuid

if __package__:
    from .sedentary_care import CareMachine, Config, Event
    from .weekly_store import WeeklyStore
    from .local_care_store import _key
    from .shadow_mode import ShadowRunner, TrackerBaseline, region_candidate
else:
    from sedentary_care import CareMachine, Config, Event
    from weekly_store import WeeklyStore
    from local_care_store import _key
    from shadow_mode import ShadowRunner, TrackerBaseline, region_candidate


@dataclass(frozen=True)
class RuntimeConfig:
    db_path: Path
    person_ids: tuple
    model_version: str
    mode: str = 'shadow'
    region_id: str = 'unknown'
    machine: Config = field(default_factory=Config)
    sync_enabled: bool = False
    token_env: str = 'AI_GUARDIAN_CARE_API_TOKEN'
    weekly_enabled: bool = False
    weekly_regions: tuple = ('unknown',)

    def __post_init__(self):
        _key(self.model_version, 'model_version')
        _key(self.region_id, 'region_id')
        if type(self.weekly_enabled) is not bool or not isinstance(self.weekly_regions,tuple) or not 1 <= len(self.weekly_regions) <= 15 or len(set(self.weekly_regions)) != len(self.weekly_regions):
            raise ValueError('invalid weekly configuration')
        for region in self.weekly_regions:
            _key(region,'weekly_region')
        if self.weekly_enabled and self.region_id not in self.weekly_regions:
            raise ValueError('default region must be registered')
        if self.mode not in ('shadow','live') or type(self.sync_enabled) is not bool:
            raise ValueError('invalid care mode or sync flag')
        if self.sync_enabled and self.mode != 'live':
            raise ValueError('shadow mode cannot enable live delivery')
        if (not isinstance(self.person_ids, tuple) or not 1 <= len(self.person_ids) <= 32
                or len(set(self.person_ids)) != len(self.person_ids)):
            raise ValueError('configure 1..32 unique stable person IDs')
        for person in self.person_ids:
            _key(person, 'person_id')
        if self.token_env != 'AI_GUARDIAN_CARE_API_TOKEN':
            raise ValueError('use the dedicated private care API token environment variable')


class SystemClock:
    def __init__(self):
        self.origin = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=time.monotonic())

    @property
    def now(self):
        return time.monotonic()

    def wall_at(self, seconds):
        return self.origin + timedelta(seconds=seconds)


class CareRuntime:
    def __init__(self, config, *, clock=None):
        self.config, self.clock = config, clock or SystemClock()
        self._lock, self._closed = threading.RLock(), False
        self._flush_lock = threading.Lock()
        self._shadow_history = deque(maxlen=100)
        self._stores, self._machines, self._active = {}, {}, {}
        self._coverage = {}
        self._regions = {}
        self.history = self.recorder = None
        self.shadow = ShadowRunner(TrackerBaseline(), region_candidate, max_pending=2)
        for person in config.person_ids:
            store = WeeklyStore(config.db_path, person, config.model_version, clock=self.utc)
            self._stores[person] = store
            session = store.session(config.mode)
            machine = (CareMachine.restore(self.clock, session['checkpoint'], config.machine)
                       if session else CareMachine(self.clock, config.machine))
            self._machines[person] = machine
            self._active[person] = session['active_event_id'] if session and machine.phase != 'IDLE' else None
            if session and session['active_event_id'] and machine.phase == 'IDLE':
                expiry = next((t for t in machine.transitions if t['event']=='uncertainty_expired'), None)
                store.save_step(config.mode, machine.checkpoint(), None, closed_id=session['active_event_id'],
                                closed_at=datetime.fromisoformat(expiry['snapshot']['wall_time']).timestamp() if expiry else None)

    def utc(self):
        return self.clock.wall_at(self.clock.now).timestamp()

    def process_frame(self, alerts, new_events):
        return process_care_frame(self, alerts, new_events)

    def store(self, person):
        if person not in self._stores:
            raise LookupError('person not configured')
        return self._stores[person]

    def state(self, person):
        self.store(person)
        with self._lock:
            return self._machines[person].snapshot()

    def events(self, person):
        return self.store(person).events(self.config.mode)

    def pending(self, person):
        return self.store(person).pending()

    def _ref(self, person, kind, event_id=None):
        return {'person_id': person, 'model_version': self.config.model_version,
                'event_id': event_id or uuid.uuid4().hex, 'mode': self.config.mode,
                'kind': kind, 'region_id': self._regions.get(person,self.config.region_id), 'started_at': self.utc(), 'ended_at': None}

    def weekly(self, person, week_start, offset_minutes=480):
        if not self.config.weekly_enabled:
            raise RuntimeError('weekly reporting is disabled')
        # Store obtains its own consistent SQLite read snapshot; calculation
        # must not hold the detection lock during a potentially large report.
        return self.store(person).weekly(self.config.mode,week_start,
            regions=self.config.weekly_regions,offset_minutes=offset_minutes)

    def erase_person(self, person):
        # Same lock order as flush: wait for any in-flight send before erasing.
        with self._flush_lock, self._lock:
            result = self.store(person).erase()
            self._coverage.pop(person,None)
            self._regions.pop(person,None)
            self._active[person] = None
            self._machines[person] = CareMachine(self.clock,self.config.machine)
            # Reports may mix several people; discard the entire ephemeral
            # comparison cache rather than retain deleted derived statistics.
            self.shadow.close()
            self.shadow = ShadowRunner(TrackerBaseline(),region_candidate,max_pending=2)
            self._shadow_history.clear()
            return result

    def resume_person(self, person):
        with self._lock:
            return self.store(person).resume()

    def _weekly_observe(self, person, rows=None):
        if not self.config.weekly_enabled:
            return
        now = self.utc()
        previous = self._coverage.get(person)
        if previous:
            start, expiry, region, valid, quality = previous
            end = min(now,expiry)
            if end > start:
                self.store(person).coverage(self.config.mode,region,start,end,valid=valid,quality=quality)
                self._coverage[person] = (end,expiry,region,valid,quality)
        if rows is not None:
            # Explicit missing detections stop coverage; downtime is never inferred.
            self._coverage.pop(person,None)
            if rows:
                row = rows[0]
                quality = row.get('care_quality')
                valid = len(rows)==1 and row.get('pose_reliable') is not False
                if quality is not None and (type(quality) not in (int,float) or not 0 <= quality <= 1):
                    quality, valid = None, False
                region = row.get('care_region_id',self.config.region_id)
                if region not in self.config.weekly_regions:
                    region='unknown'
                self._regions[person] = region
                self._coverage[person] = (now,now+30,region,valid,quality)
        self.store(person).maintain(self.config.mode)

    def _step(self, person, event):
        store, machine = self.store(person), self._machines[person]
        previous_id = self._active[person]
        ordinal = sum(machine.counts.values())
        before_records = len(machine.speaker.records)
        before_traces = len(machine.transitions)
        snapshot = machine.handle(event)
        expired = next((t for t in machine.transitions[before_traces:]
                        if t['event'] == 'uncertainty_expired'), None)
        created = None
        if machine.phase != 'IDLE' and (previous_id is None or expired) and event == Event.SIT:
            created = self._ref(person, 'sit')
            self._active[person] = created['event_id']
        messages = []
        for index, record in enumerate(machine.speaker.records[before_records:], ordinal + 1):
            identity = (previous_id if expired and record['at'] <= expired['at'] else
                        self._active[person] or previous_id)
            if identity is None:
                raise RuntimeError('broadcast without a durable event identity')
            messages.append({'schema_version': 1, 'event_id': identity, 'person_id': person,
                             'model_version': self.config.model_version, 'revision': index, **record})
        closed = previous_id if machine.phase == 'IDLE' or expired else None
        if closed and machine.phase == 'IDLE':
            self._active[person] = None
        try:
            store.save_step(self.config.mode, machine.checkpoint(), self._active[person],
                            event=created, closed_id=closed, messages=messages,
                            closed_at=datetime.fromisoformat(expired['snapshot']['wall_time']).timestamp() if expired else None)
        except BaseException:
            # Recover from committed state on the next call; never keep an
            # uncommitted in-memory level/identity after a disk failure.
            session = store.session(self.config.mode)
            self._machines[person] = (CareMachine.restore(self.clock, session['checkpoint'], self.config.machine)
                                      if session else CareMachine(self.clock, self.config.machine))
            self._active[person] = session['active_event_id'] if session else None
            raise
        machine.speaker.records.clear()
        machine.transitions.clear()
        return {'person_id': person, 'snapshot': snapshot, 'broadcasts': messages}

    def _person(self, alert):
        person = alert.get('care_person_id')
        if person is None and str(alert.get('face_label', '')).startswith('known:'):
            person = alert['face_label'][6:]
        return person if person in self._stores else None

    def on_detection(self, alerts, new_events):
        with self._lock:
            if self._closed:
                raise RuntimeError('care runtime is closed')
            self._shadow_history.extend(self.shadow.pop_completed())
            alerts = [a for a in alerts if not (self._person(a) and self.store(self._person(a)).erased())]
            by_person = {}
            for alert in alerts:
                person = self._person(alert)
                if person:
                    by_person.setdefault(person, []).append(alert)
            states, record_refs, refs, normalized = [], [], {}, []
            for person in self.config.person_ids:
                if self.store(person).erased():
                    continue
                rows = by_person.get(person, [])
                self._weekly_observe(person,rows)
                if len(rows) > 1:
                    event = Event.LOW_CONFIDENCE
                elif not rows:
                    event = Event.TARGET_LOST if self._machines[person].phase != 'IDLE' else Event.TIMEOUT
                else:
                    alert = rows[0]
                    event = (Event.LOW_CONFIDENCE if alert.get('pose_reliable') is False else
                             Event.NON_SIT if 'FALL' in alert.get('status', '') else
                             Event.SIT if alert.get('is_sitting') is True else
                             Event.NON_SIT if alert.get('is_sitting') is False else Event.MISSING)
                step = self._step(person, event)
                states.append(step)
                if self.config.mode == 'live' and step['broadcasts']:
                    identity = step['broadcasts'][0]['event_id']
                    record_refs.append(self.store(person).event(identity, self.config.mode))
            at_ms = int(self.utc() * 1000)
            for kind in ('fall','sit','stranger'):
                for alert in new_events.get(kind, []):
                    person = self._person(alert)
                    if person is None or self.store(person).erased():
                        continue
                    identity = self._active[person] if kind == 'sit' else None
                    ref = self.store(person).event(identity, self.config.mode) if identity else None
                    if ref is None:
                        ref = self._ref(person, kind)
                        self.store(person).create_event(ref)
                    if self.config.mode == 'live':
                        refs[(kind, alert['id'])] = ref
                    normalized.append({'event_id': ref['event_id'], 'person_id': person,
                                       'model_version': self.config.model_version, 'region_id': ref['region_id'],
                                       'kind': kind, 'start_ms': at_ms, 'end_ms': at_ms})
            self.shadow.run({'query': {'start_ms': at_ms, 'end_ms': at_ms + 1},
                             'frames': [{'at_ms': at_ms, 'model_version': self.config.model_version,
                                         'alerts': [{k: a[k] for k in ('id','status','is_sitting','face_label') if k in a}
                                                    for a in alerts]}], 'events': normalized})
            return {'states': states, 'event_refs': refs, 'record_refs': record_refs,
                    'mode': self.config.mode}

    def tick(self):
        with self._lock:
            if self._closed:
                raise RuntimeError('care runtime is closed')
            results = []
            for person in self.config.person_ids:
                if self.store(person).erased():
                    continue
                self._weekly_observe(person)
                results.append(self._step(person,Event.TIMEOUT))
            if self.config.mode == 'live':
                for result in results:
                    result['recording_errors'] = []
                    for message in result['broadcasts']:
                        ref = self.store(result['person_id']).event(message['event_id'], self.config.mode)
                        error = attempt_recording(self.recorder, ref)
                        if error:
                            result['recording_errors'].append(error)
            return results

    def feedback(self, person, event_id, payload=None, *, operation='submit', reason=''):
        with self._lock:
            if self._closed:
                raise RuntimeError('care runtime is closed')
            return self.store(person).event_feedback(event_id, self.config.mode, payload,
                                                     operation=operation, reason=reason)

    def flush(self, sender):
        delivered, failed = 0, 0
        if self.config.mode != 'live':
            return {'delivered': 0, 'failed': 0}
        with self._flush_lock:
            for person in self.config.person_ids:
                for record in self.pending(person):
                    try:
                        ack = sender(record) is True
                        code = None if ack else 'no_ack'
                    except Exception as exc:
                        ack, code = False, type(exc).__name__
                    self.store(person).ack(record['message_id'], delivered=ack, error=code)
                    if not ack:
                        failed += 1
                        return {'delivered': delivered, 'failed': failed}
                    delivered += 1
        return {'delivered': delivered, 'failed': failed}

    def drain_shadow(self):
        self.shadow.drain()
        with self._lock:
            self._shadow_history.extend(self.shadow.pop_completed())

    def shadow_reports(self):
        with self._lock:
            return deepcopy(list(self._shadow_history) + self.shadow.reports())

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self.shadow.close()


def record_event(cache, ref):
    """Register the exact care ID before linking it to an existing clip."""
    if cache is None or ref is None:
        return None
    row = cache.store.get_event(ref['event_id'])
    if row is None:
        cache.store.add_event(ref['kind'], ref['started_at'], person_id=ref['person_id'],
                              event_id=ref['event_id'], payload={'model_version': ref['model_version']})
    elif row['kind'] != ref['kind'] or row['person_id'] != ref['person_id']:
        raise ValueError('recording event identity collision')
    return cache.trigger(event_id=ref['event_id'])


def attempt_recording(cache, ref):
    try:
        record_event(cache, ref)
        return None
    except Exception as exc:
        error = {'stage':'recording', 'event_id':ref['event_id'], 'code':type(exc).__name__}
        print(f"[Care] recording_failed event_id={ref['event_id']} code={type(exc).__name__}")
        return error


def process_care_frame(runtime, alerts, new_events):
    """Actual detection-entry seam, executable without importing board hardware."""
    if runtime is None:
        return {'mode': 'off', 'states': [], 'event_refs': {}, 'record_refs': []}
    result = runtime.on_detection(alerts, new_events)
    result['recording_errors'] = []
    if runtime.config.mode == 'live':
        for ref in result['record_refs']:
            error = attempt_recording(runtime.recorder, ref)
            if error:
                result['recording_errors'].append(error)
    return result


def runtime_from_env(environ=None):
    env = os.environ if environ is None else environ
    source = env.get('AI_GUARDIAN_CARE_CONFIG')
    if not source:
        return None
    path = Path(source)
    raw = json.loads(path.read_text(encoding='utf-8'))
    if raw.get('mode', 'off') == 'off':
        return None
    allowed = {f.name for f in fields(RuntimeConfig)}
    if set(raw) - allowed:
        raise ValueError('unknown/private values are not accepted in care config')
    machine = dict(raw.pop('machine', {}))
    for name in ('quiet_start','quiet_end'):
        if name in machine and machine[name] is not None:
            machine[name] = wall_time.fromisoformat(machine[name])
    raw['machine'] = Config(**machine)
    raw['person_ids'] = tuple(raw['person_ids'])
    if 'weekly_regions' in raw:
        raw['weekly_regions'] = tuple(raw['weekly_regions'])
    raw['db_path'] = path.parent / raw['db_path']
    return CareRuntime(RuntimeConfig(**raw))
