"""Local delivery chain: real machine/stores, virtual time, no online output."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import ast
from functools import lru_cache
import sys
import threading
import tempfile
import unittest

from src.care_runtime import CareRuntime, RuntimeConfig, process_care_frame
from src.sedentary_care import VirtualClock
from src.guardian_runtime import AlertEpisodeTracker

RESULTS = {}

ROOT = Path(__file__).resolve().parent


@lru_cache(maxsize=2)
def production_entry(name):
    """Execute the actual source entry without importing its hardware startup."""
    from src.care_runtime import process_care_frame, record_event
    tree = ast.parse((ROOT / 'src/ascend_board_server.py').read_text(encoding='utf-8'))
    node = next(n for n in tree.body if getattr(n, 'name', '') == name)
    namespace = {'process_care_frame': process_care_frame, 'record_event': record_event}
    exec(compile(ast.Module(body=[node], type_ignores=[]), 'ascend_board_server.py', 'exec'), namespace)
    return namespace[name]


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.clock = VirtualClock(datetime(2026, 11, 16, 12, tzinfo=timezone(timedelta(hours=8))))
        self.config = RuntimeConfig(db_path=Path(self.temp.name) / 'care.db',
                                    person_ids=('p1', 'p2'), model_version='test-model', mode='live')
        self.runtime = CareRuntime(self.config, clock=self.clock)
        self.legacy_tracker = AlertEpisodeTracker()
        self.addCleanup(lambda: self.runtime.close())

    def observe(self, persons=('p1',)):
        alerts = [dict(id=i, care_person_id=p, is_sitting=True, face_label='known:' + p)
                  for i, p in enumerate(persons)]
        new_events = self.legacy_tracker.update(alerts, self.runtime.utc())
        result = production_entry('dispatch_care_detection')(self.runtime, alerts, new_events)
        if self.runtime.recorder is not None:
            for kind in ('fall','sit','stranger'):
                for alert in new_events[kind]:
                    try:
                        production_entry('trigger_history_event')(self.runtime.recorder, kind, alert, result, self.runtime.utc())
                    except Exception as exc:
                        # The actual inference loop catches this boundary too;
                        # retain the error instead of converting to another ID.
                        result.setdefault('legacy_recording_errors', []).append(type(exc).__name__)
        return result

    def sit(self, seconds=1800, persons=('p1',)):
        self.observe(persons)
        for _ in range(seconds // 10):
            self.clock.advance(10)
            self.observe(persons)

    def test_restart_resumes_same_event_without_counting_downtime_or_repeating_l0(self):
        self.sit(900)
        original = self.runtime.events('p1')[0]['event_id']
        self.runtime.close()
        self.clock.advance(5)
        self.clock = VirtualClock(self.clock.wall_at(self.clock.now))
        self.runtime = CareRuntime(self.config, clock=self.clock)
        self.assertEqual(self.runtime.state('p1')['state'], 'PAUSED')
        self.sit(900)
        self.assertEqual(self.runtime.events('p1')[0]['event_id'], original)
        self.assertEqual(self.runtime.state('p1')['seated_seconds'], 1800)
        self.assertEqual(self.runtime.state('p1')['counts'], {'L0': 1, 'L1': 0})
        self.assertEqual(len(self.runtime.pending('p1')), 1)
        RESULTS['restart'] = {'expected': {'same_id': True, 'seated_seconds': 1800, 'l0': 1, 'pending': 1},
                             'actual': {'same_id': self.runtime.events('p1')[0]['event_id'] == original,
                                        'seated_seconds': self.runtime.state('p1')['seated_seconds'],
                                        'l0': self.runtime.state('p1')['counts']['L0'],
                                        'pending': len(self.runtime.pending('p1'))}, 'event_id': original}
        self.runtime.close()
        self.runtime = CareRuntime(self.config, clock=self.clock)
        self.observe()
        self.assertEqual(len(self.runtime.pending('p1')), 1)

    def test_duplicate_feedback_uses_original_id_and_occurrence_time(self):
        self.sit()
        identity = self.runtime.events('p1')[0]['event_id']
        first = self.runtime.feedback('p1', identity, {'label': 'normal'})
        self.clock.advance(10)
        second = self.runtime.feedback('p1', identity, {'label': 'corrected'})
        self.assertEqual(first['target_id'], identity)
        self.assertEqual(second['target_id'], identity)
        self.assertEqual(first['created_at'], second['created_at'])
        self.assertEqual(second['payload'], {'label': 'corrected'})
        self.assertEqual(self.runtime.store('p1').count_feedback(), 1)
        self.assertEqual(self.runtime.store('p2').count_feedback(status='all'), 0)
        RESULTS['duplicate_feedback'] = {'expected': {'rows':1, 'same_id':True, 'same_created':True},
            'actual': {'rows':self.runtime.store('p1').count_feedback(), 'same_id':second['target_id']==identity,
                       'same_created':first['created_at']==second['created_at']},
            'event_id':identity, 'feedback_target_id':second['target_id'], 'payload':second['payload']}
        with self.assertRaises(LookupError):
            self.runtime.feedback('p2', identity, {'label': 'wrong scope'})

    def test_revoke_hidden_and_retained_for_audit_and_sync(self):
        self.sit()
        identity = self.runtime.events('p1')[0]['event_id']
        self.runtime.feedback('p1', identity, {'label': 'normal'})
        self.runtime.feedback('p1', identity, operation='revoke', reason='changed mind')
        self.assertIsNone(self.runtime.store('p1').get_feedback(identity, self.runtime.events('p1')[0]['started_at']))
        row = self.runtime.store('p1').list_feedback(status='revoked')[0]
        self.assertEqual(row['target_id'], identity)
        self.assertEqual(len(self.runtime.store('p1').feedback_audit(identity, row['event_at'], status='all')), 2)
        feedback_messages = [m for m in self.runtime.pending('p1') if m['message_type'] == 'feedback']
        self.assertTrue(feedback_messages[-1]['payload']['feedback']['is_revoked'])
        RESULTS['revoke'] = {'expected': {'active':0,'revoked':1,'audit_rows':2},
            'actual': {'active':self.runtime.store('p1').count_feedback(),
                       'revoked':self.runtime.store('p1').count_feedback(status='revoked'),
                       'audit_rows':len(self.runtime.store('p1').feedback_audit(identity,row['event_at'],status='all'))},
            'event_id':identity}

    def test_offline_restart_then_retry_keeps_idempotency_key_until_ack(self):
        self.sit()
        identity = self.runtime.events('p1')[0]['event_id']
        self.runtime.feedback('p1', identity, {'label': 'normal'})
        original = [r['message_id'] for r in self.runtime.pending('p1')]
        def offline(message):
            raise ConnectionError('simulated offline')
        result = self.runtime.flush(offline)
        self.assertEqual(result['delivered'], 0)
        self.runtime.close()
        self.runtime = CareRuntime(self.config, clock=self.clock)
        attempts = []
        self.runtime.flush(lambda message: attempts.append(message['message_id']) or False)
        self.assertEqual(attempts, original[:1])
        sent = []
        result = self.runtime.flush(lambda message: sent.append(message) or True)
        self.assertEqual([m['message_id'] for m in sent], original)
        self.assertTrue(all(m['event_id'] == identity for m in sent))
        self.assertEqual(result['delivered'], len(original))
        self.assertEqual(self.runtime.pending('p1'), [])
        RESULTS['offline_retry'] = {'expected': {'same_message_ids':True,'pending':0,'delivered':2},
            'actual': {'same_message_ids':[m['message_id'] for m in sent]==original,
                       'pending':len(self.runtime.pending('p1')),'delivered':result['delivered']},
            'event_id':identity,'message_ids':original}

    def test_shadow_cannot_trigger_recording_or_live_queue(self):
        self.runtime.close()
        from dataclasses import replace
        self.runtime = CareRuntime(replace(self.config, mode='shadow'), clock=self.clock)
        touched = []
        legacy_calls = []
        class Trap:
            @property
            def store(self):
                touched.append('recording')
                raise AssertionError('shadow touched recording')
            def trigger(self, *args, **kwargs):
                legacy_calls.append(kwargs)
                return {'event_id':'legacy-only'}
        self.runtime.recorder = Trap()
        self.sit()
        self.assertEqual(self.runtime.state('p1')['level'], 'L0')
        self.assertEqual(self.runtime.pending('p1'), [])
        called = []
        self.assertEqual(self.runtime.flush(lambda message: called.append(message) or True)['delivered'], 0)
        self.assertEqual(called, [])
        self.assertEqual(touched, [])
        self.assertTrue(legacy_calls)
        self.assertTrue(all('event_id' not in call for call in legacy_calls))
        self.runtime.drain_shadow()
        self.assertTrue(self.runtime.shadow_reports())

    def test_two_real_state_events_share_one_real_recording_index(self):
        sys.path.insert(0, str(ROOT / 'src'))
        import numpy as np
        from guardian_event_cache import EventClipCache
        from guardian_history import HistoryStore
        from guardian_recording_config import RecordingConfig
        from guardian_recording import SegmentArtifact
        from guardian_storage import initialize_storage
        config = RecordingConfig(enabled=True, data_root=Path(self.temp.name) / 'clips',
            storage_quota_bytes=10000000, min_free_bytes=1, encoder='test-only-fake',
            pre_roll_seconds=0, post_roll_seconds=1, event_clip_max_seconds=10)
        initialize_storage(config)
        history = HistoryStore(config)
        ready = threading.Event()
        completed = []
        class Backend:
            def start(self, partial, final, metadata):
                self.partial, self.final, self.metadata = partial, final, metadata
                partial.write_bytes(b'FAKE NOT VIDEO\n')
            def write(self, packet):
                with self.partial.open('ab') as stream:
                    stream.write(packet.data)
            def finish(self):
                self.partial.rename(self.final)
                return SegmentArtifact(self.metadata['relpath'], self.final.stat().st_size, True, 0)
            def abort(self):
                pass
        def on_ready(event_ids, recording_id):
            completed.append((event_ids, recording_id))
            ready.set()
        cache = EventClipCache(config, history, lambda _: Backend(), clock=self.runtime.utc,
                               monotonic=lambda: self.clock.now, on_clip_ready=on_ready)
        self.assertTrue(cache.start())
        try:
            self.sit(1790, persons=('p1','p2'))
            self.runtime.recorder = cache
            self.clock.advance(10)
            self.observe(('p1','p2'))
            ids = {self.runtime.events(p)[0]['event_id'] for p in ('p1','p2')}
            self.assertEqual(set(cache.status()['last_clip']['event_ids']) if cache.status()['last_clip'] else set(cache._clip.event_ids), ids)
            self.assertTrue(cache.submit_frame(np.zeros((48,64,3), dtype=np.uint8), captured_at=self.runtime.utc(), monotonic_at=self.clock.now))
            self.clock.advance(2)
            cache._wake.set()
            self.assertTrue(ready.wait(5), cache.status())
            self.assertEqual(set(completed[0][0]), ids)
            recordings = [history.list_event_recordings(identity)[0]['id'] for identity in ids]
            self.assertEqual(len(set(recordings)), 1)
            RESULTS['shared_recording'] = {'expected':{'events':2,'recordings':1,'linked_events':2},
                'actual':{'events':len(ids),'recordings':len(set(recordings)),
                          'linked_events':cache.status()['last_clip']['linked_events']},
                'event_ids':sorted(ids),'recording_id':recordings[0]}
            for person in ('p1','p2'):
                identity = self.runtime.events(person)[0]['event_id']
                feedback = self.runtime.feedback(person, identity, {'label':'same-clip'})
                self.assertEqual(feedback['target_id'], identity)
        finally:
            cache.stop(timeout=5)
            history.close()

    def test_long_gap_creates_new_id_and_new_l0_queue_revision(self):
        self.sit()
        first = self.runtime.events('p1')[0]['event_id']
        self.clock.advance(200)
        self.observe()
        second = self.runtime.events('p1')[-1]['event_id']
        self.assertNotEqual(first, second)
        self.sit()
        reminders = [m for m in self.runtime.pending('p1') if m['message_type']=='reminder']
        self.assertEqual({m['event_id'] for m in reminders}, {first,second})

    def test_tick_reminder_reaches_same_recording_identity(self):
        self.sit(1790)
        captured = []
        class History:
            def get_event(self, identity):
                return None
            def add_event(self, kind, at, **kwargs):
                captured.append(kwargs['event_id'])
        class Recorder:
            store = History()
            def trigger(self, **kwargs):
                captured.append(kwargs['event_id'])
        self.runtime.recorder = Recorder()
        identity = self.runtime.events('p1')[0]['event_id']
        self.clock.advance(10)
        self.runtime.tick()
        self.assertEqual(captured, [identity, identity])
        self.assertEqual(self.runtime.pending('p1')[0]['event_id'], identity)

    def test_feedback_and_outbox_roll_back_together(self):
        from src.local_care_migrations import connection
        self.sit()
        identity = self.runtime.events('p1')[0]['event_id']
        with connection(self.config.db_path) as db:
            db.execute("CREATE TRIGGER fail_queue BEFORE INSERT ON care_outbox BEGIN SELECT RAISE(ABORT,'simulated disk failure'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.runtime.feedback('p1', identity, {'label':'normal'})
        self.assertEqual(self.runtime.store('p1').count_feedback(status='all'), 0)
        self.assertEqual(len(self.runtime.pending('p1')), 1)

    def test_recording_failure_keeps_processed_state_and_event_id(self):
        self.sit(1790)
        identity = self.runtime.events('p1')[0]['event_id']
        class Broken:
            @property
            def store(self):
                raise OSError('simulated recording disk failure')
            def trigger(self, *args, **kwargs):
                raise OSError('simulated legacy recording disk failure')
        self.runtime.recorder = Broken()
        self.clock.advance(10)
        result = self.observe()
        self.assertEqual(result['mode'], 'live')
        self.assertEqual(result['recording_errors'][0]['event_id'], identity)
        self.assertEqual(self.runtime.pending('p1')[0]['event_id'], identity)
        self.assertEqual(self.runtime.feedback('p1', identity, {'label':'no-video'})['target_id'], identity)

    def test_long_restart_expires_old_session_without_reusing_id(self):
        self.sit(10)
        original = self.runtime.events('p1')[0]['event_id']
        self.runtime.close()
        self.clock.advance(200)
        self.clock = VirtualClock(self.clock.wall_at(self.clock.now))
        self.runtime = CareRuntime(self.config, clock=self.clock)
        self.assertEqual(self.runtime.state('p1')['state'], 'IDLE')
        self.assertIsNotNone(self.runtime.events('p1')[0]['ended_at'])
        self.observe()
        self.assertNotEqual(self.runtime.events('p1')[-1]['event_id'], original)

    def test_no_config_is_off_and_secrets_are_rejected_before_db_creation(self):
        from src.care_runtime import runtime_from_env
        import json
        self.assertIsNone(runtime_from_env({}))
        private = Path(self.temp.name) / 'invalid.json'
        private.write_text(json.dumps({'mode':'shadow','db_path':'should-not-exist.db',
            'person_ids':['p1'],'model_version':'m1','api_token':'never-store-this'}), encoding='utf-8')
        with self.assertRaises(ValueError):
            runtime_from_env({'AI_GUARDIAN_CARE_CONFIG':str(private)})
        self.assertFalse((private.parent / 'should-not-exist.db').exists())
        from dataclasses import replace
        with self.assertRaises(ValueError):
            replace(self.config, mode='shadow', sync_enabled=True)

    def test_mqtt_transport_only_new_topics_and_ack_required(self):
        from src.care_transport import MqttCareSender
        self.sit()
        captured = []
        class Receipt:
            rc = 0
            def wait_for_publish(self, timeout):
                captured.append(('wait',timeout))
            def is_published(self):
                return True
        class Client:
            def publish(self, topic, payload, qos):
                captured.append((topic,qos))
                return Receipt()
        record = self.runtime.pending('p1')[0]
        self.assertTrue(MqttCareSender(Client())(record))
        self.assertEqual(captured[0], ('ai_guardian/care/reminders',1))
        with self.assertRaises(ValueError):
            MqttCareSender(Client())({**record,'mode':'shadow'})

    def test_v2_to_v3_keeps_existing_feedback_bytes_and_backup(self):
        from src.local_care_migrations import migrate_database, connection
        path = Path(self.temp.name) / 'v2.db'
        migrate_database(path, target_version=2)
        with connection(path) as db:
            db.execute("INSERT INTO feedback VALUES ('p1','m1','old-event',600,601,'{}',1000,1000,0,NULL,NULL,1)")
            before = tuple(db.execute('SELECT * FROM feedback').fetchone())
        result = migrate_database(path, target_version=3)
        with connection(path) as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM feedback').fetchone()), before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 3)
        with connection(result['backup_path']) as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM feedback').fetchone()), before)
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 2)

    def test_authenticated_api_keeps_id_and_refuses_target_override(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from src.care_api import create_care_router
        app = FastAPI()
        app.include_router(create_care_router(self.runtime, token_provider=lambda: 'synthetic-test-token'))
        self.sit()
        with TestClient(app) as client:
            prefix = '/api/care/test-model/p1'
            self.assertEqual(client.get(prefix + '/events').status_code, 401)
            client.headers['Authorization'] = 'Bearer synthetic-test-token'
            identity = client.get(prefix + '/events').json()['events'][0]['event_id']
            path = prefix + '/events/' + identity + '/feedback'
            self.assertEqual(client.post(path, json={'payload': {'label':'normal'}}).json()['target_id'], identity)
            self.assertEqual(client.post(path, json={'payload': {}, 'event_id':'replacement'}).status_code, 422)
            self.assertEqual(client.post(path.replace('/p1/', '/p2/'), json={'payload': {}}).status_code, 404)
            self.assertEqual(client.post(path.replace('/test-model/', '/other-model/'), json={'payload': {}}).status_code, 404)
            self.assertEqual(client.post(path, json={'operation':'revoke'}).status_code, 200)
            self.assertEqual(client.get(prefix + '/feedback').json()['feedback'], [])
            self.assertEqual(len(client.get(prefix + '/feedback?status=revoked').json()['feedback']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
