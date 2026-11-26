import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from pathlib import Path

from src.personalization_v5 import ProtocolError, Store, iso, validate


NOW = 1795651200.0


def reminder(event='e1', **extra):
    return dict(schema_version='2', event_id=event, alert_type='late_wakeup',
                timestamp=iso(NOW), expires_at=iso(NOW+120), reason='合成测试：尚在床区', **extra)


def result(revision=1, response='ok', event='e1', **extra):
    return dict(schema_version='2', event_id=event, revision=revision, status='completed',
                timestamp=iso(NOW+30), response=response, **extra)


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now = NOW+1
        self.path = Path(self.tmp.name)/'model.sqlite'
        self.model = Store(self.path, 'test-device', 'model', clock=lambda: self.now)
        self.peer = Store(Path(self.tmp.name)/'peer.sqlite', 'test-device', 'peer', clock=lambda: self.now)

    def assert_code(self, code, fn):
        with self.assertRaises(ProtocolError) as caught:
            fn()
        self.assertEqual(caught.exception.code, code)

    def test_validation_and_wire_enums(self):
        for change in ({'schema_version': 2}, {'schema_version': '3'}):
            self.assert_code(422, lambda: validate({**reminder(), **change}, 'reminder', 'test-device'))
        for change in ({'device_id': 'other'}, {'reason': ' '}, {'timestamp': '2026-11-26T08:00:00'},
                       {'expires_at': iso(NOW)}, {'event_id': None}):
            self.assert_code(400, lambda: self.model.accept_reminder({**reminder(), **change}))
        for change in ({'revision': True}, {'response': 'okay'}, {'error_code': 'input_unavailable'},
                       {'prompted_at': None}, {'status': 'error', 'response': 'ok'}, {'response': []}):
            self.assert_code(400, lambda: validate({**result(), **change}, 'result', 'test-device'))

    def test_semantic_duplicate_and_optional_presence_conflict_after_expiry(self):
        self.assertEqual(self.model.accept_reminder(reminder())['disposition'], 'accepted')
        same = {**reminder(), 'timestamp': '2026-11-26T08:00:00+08:00', 'irrelevant': 'ignored'}
        self.now += 121
        self.assertEqual(self.model.accept_reminder(same)['disposition'], 'duplicate')
        for changed in ({'reason': 'changed'}, {'device_id': 'test-device'}):
            self.assert_code(409, lambda: self.model.accept_reminder({**reminder(), **changed}))
        self.assertEqual(self.model.accept_reminder(reminder('expired'))['disposition'], 'expired')

    def test_busy_slot_reserved_in_same_transaction_and_survives_new_instance(self):
        gate = threading.Barrier(2)
        outcomes = []
        def accept(name):
            gate.wait()
            try: outcomes.append(self.model.accept_reminder(reminder(name))['disposition'])
            except ProtocolError as error: outcomes.append(error.code)
        threads = [threading.Thread(target=accept, args=(name,)) for name in ('a','b')]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(outcomes, ['accepted', 503])
        self.assert_code(503, lambda: Store(self.path, 'test-device', 'model', clock=lambda:self.now).accept_reminder(reminder('c')))

    def test_result_before_reminder_ack_matches_registered_event(self):
        self.peer.register_reminder(reminder())
        ack = self.peer.accept_result(result())
        self.assertEqual(ack['revision'], 1)
        self.assertEqual(self.peer.pending(), [])
        self.assertEqual(self.peer.event('e1')['latest']['response'], 'ok')
        self.assert_code(404, lambda:self.peer.accept_result(result(event='unknown')))

    def test_lower_version_help_is_sticky_and_task_is_exactly_once(self):
        self.peer.register_reminder(reminder())
        self.peer.accept_result(result(3, 'ok'))
        self.peer.accept_result(result(2, 'needs_help'))
        self.peer.accept_result(result(4, 'unclear'))
        self.assertEqual(self.peer.accept_result(result(2, 'needs_help'))['disposition'], 'duplicate')
        event = self.peer.event('e1')
        self.assertEqual(event['latest']['revision'], 4)
        self.assertTrue(event['help_required'])
        self.assertEqual(len(self.peer.help_tasks()), 1)
        self.assert_code(409, lambda:self.peer.accept_result(result(2, 'ok')))

    def test_atomic_result_versions_window_and_original_outbox_survive_restart(self):
        self.model.accept_reminder(reminder())
        first = self.model.complete('e1', response='no_response')
        self.now += 299
        second = self.model.complete('e1', response='needs_help', received_at=self.now)
        self.assertEqual(second['revision'], 2)
        self.assertEqual(self.model.complete('e1', response='ok', received_at=self.now), second)
        restored = Store(self.path, 'test-device', 'model', clock=lambda:self.now)
        self.assertEqual([x['payload'] for x in restored.pending()], [first, second])
        self.assertEqual(restored.event('e1')['late_until'], NOW+301)

    def test_late_window_uses_input_time_not_completion_time(self):
        self.model.accept_reminder(reminder())
        self.model.complete('e1', response='unclear')
        received = self.now+299
        self.now += 303
        upgraded = self.model.complete('e1', response='needs_help', received_at=received)
        self.assertEqual(upgraded['revision'], 2)
        self.model.accept_reminder({**reminder('e2'), 'timestamp':iso(self.now), 'expires_at':iso(self.now+120)})
        self.model.complete('e2', response='no_response')
        self.now += 300
        self.assert_code(410, lambda:self.model.complete('e2', response='needs_help', received_at=self.now))

    def test_retry_schedule_ack_validation_and_per_version_deadlines(self):
        self.model.accept_reminder(reminder())
        payload = self.model.complete('e1', response='needs_help')
        for delay in (5,15,30,60):
            item = self.model.pending()[0]
            bad = dict(schema_version='2', event_id='e1', disposition='accepted')
            self.model.record_delivery(item['id'], 200, bad)
            self.assertEqual(self.model.pending(), [])
            self.now += delay
            self.assertEqual(self.model.pending()[0]['payload'], payload)
        item = self.model.pending()[0]
        self.model.record_delivery(item['id'], 200, dict(schema_version='2',event_id='e1',revision=1,disposition='expired'))
        self.now += 86400
        self.assertEqual(self.model.pending(), [])
        self.assertTrue(self.model.failed_deliveries())
        self.assertEqual(self.model.event('e1')['latest'], payload)

    def test_valid_ack_and_permanent_errors_stop_retries(self):
        self.peer.register_reminder(reminder())
        item = self.peer.pending()[0]
        self.peer.record_delivery(item['id'], 200, dict(schema_version='2',event_id='e1',disposition='accepted'))
        self.assertEqual(self.peer.pending(), [])
        self.model.accept_reminder(reminder())
        self.model.complete('e1', response='ok')
        self.model.record_delivery(self.model.pending()[0]['id'], 404, {})
        self.assertEqual(self.model.pending(), [])
        self.assertEqual(self.model.failed_deliveries()[0]['last_error'], 'http_404')

    def test_unknown_database_or_changed_binding_is_refused(self):
        self.assertRaises(ValueError, Store, self.path, 'other-device', 'model')
        unknown=Path(self.tmp.name)/'unknown.sqlite'
        with closing(sqlite3.connect(unknown)) as db: db.execute('CREATE TABLE existing(x)')
        self.assertRaises(ValueError, Store, unknown, 'test-device', 'model')
        with closing(sqlite3.connect(unknown)) as db:
            self.assertEqual(db.execute('SELECT name FROM sqlite_master').fetchall(), [('existing',)])


if __name__ == '__main__':
    unittest.main()
