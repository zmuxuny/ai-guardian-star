from datetime import date, time, timedelta
import json
from pathlib import Path
import tempfile
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
from tools import late_wakeup_demo as replay


class LateWindowTests(unittest.TestCase):
    def test_late_baselines_remain_reachable_after_ten(self):
        for departure in (time(8, 30), time(9), time(9, 55)):
            with self.subTest(departure=departure):
                day = date(2026, 11, 24)
                history = {r.timestamp: r for r in replay.simulate_day(day-timedelta(days=1), departure)}
                typical, _ = replay.typical_departure(history)
                observations = {r.timestamp: r for r in replay.simulate_day(day, time(12))}
                out = replay.replay_day(observations, typical)
                self.assertIsNotNone(out.reminder)
                threshold = replay.at(day, departure) + timedelta(minutes=90)
                self.assertEqual(replay.read_timestamp(out.reminder['timestamp']), threshold)
                missing = observations.copy()
                missing.pop(threshold-timedelta(minutes=5))
                self.assertIsNone(replay.replay_day(missing, typical).reminder)

    def test_departure_before_late_threshold_suppresses_reminder(self):
        day = date(2026, 11, 24)
        observations = {r.timestamp: r for r in replay.simulate_day(day, time(10, 25))}
        self.assertIsNone(replay.replay_day(observations, time(9)).reminder)


class RoutineBridgeTests(unittest.TestCase):
    def setUp(self):
        from tools import personalization_routine_peer as bridge
        from tools import personalization_http as http
        from tools import routine_alert_demo as routine
        self.bridge, self.http, self.routine = bridge, http, routine
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        routine.generate(self.root)
        self.now = replay.at(date(2026, 11, 24), time(8, 30))

    def setup_app(self, name):
        self.app = self.http.Personalization(self.root/(name+'.sqlite'), lambda: self.now, 'test-device')
        return self.bridge.RoutinePeer(self.app, self.root/'history.csv')

    def test_all_rules_register_once_across_restart_and_rescan(self):
        times = (self.now, replay.at(date(2026, 11, 24), time(15)),
                 replay.at(date(2026, 11, 25), time(0)))
        for kind, now in zip(self.routine.ALERT_TYPES, times):
            self.now = now
            scanner = self.setup_app(kind)
            path = self.root/('routine-'+kind+'.csv')
            first = scanner.scan(path)
            self.assertEqual(first['registered'], 1)
            key = first['events'][0]['event_id']
            queued = self.app.queued(key)
            self.assertEqual(len(queued), 1)
            payload = json.loads(queued[0]['payload'])
            self.assertEqual(payload['alert_type'], kind)
            self.assertEqual(payload['device_id'], 'test-device')
            self.assertEqual(replay.read_timestamp(payload['timestamp']), now)
            reopened = self.http.Personalization(self.app.path, lambda: self.now, 'test-device')
            repeated = self.bridge.RoutinePeer(reopened, self.root/'history.csv').scan(path)
            self.assertEqual(repeated['registered'], 0)
            self.assertEqual(repeated['duplicates'], 1)
            self.assertEqual(reopened.queued(key)[0]['payload'], queued[0]['payload'])

    def test_future_observations_cannot_trigger_early(self):
        self.now = replay.at(date(2026, 11, 24), time(14, 55))
        scanner = self.setup_app('future')
        path = self.root/'routine-daytime_inactivity.csv'
        before = scanner.scan(path)
        self.assertEqual(before['registered'], 0)
        self.assertGreater(before['future_observations_ignored'], 0)
        self.now += timedelta(minutes=5)
        self.assertEqual(scanner.scan(path)['registered'], 1)

    def test_old_events_keep_original_expiry_and_never_send(self):
        self.now += timedelta(seconds=121)
        scanner = self.setup_app('expired')
        scan = scanner.scan(self.root/'routine-late_wakeup.csv')
        self.assertEqual((scan['registered'], scan['expired']), (1, 1))
        key = scan['events'][0]['event_id']
        original = self.app.queued(key)[0]['payload']
        self.app.flush(1)
        item = self.app.queued(key)[0]
        self.assertEqual((item['state'], item['attempts']), ('unconfirmed', 0))
        self.assertEqual(item['payload'], original)

    def test_overlapping_training_and_observations_is_rejected(self):
        scanner = self.setup_app('overlap')
        with self.assertRaises(ValueError):
            scanner.scan(self.root/'history.csv')

    def test_cli_runs_with_old_csv_without_refreshing_or_sending_expired_events(self):
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        db = self.root/'cli.sqlite'
        command = [sys.executable, '-m', 'tools.personalization_routine_peer',
                   '--history', str(self.root/'history.csv'),
                   '--observations', str(self.root/'routine-late_wakeup.csv'),
                   '--db', str(db), '--device-id', 'test-device', '--model-port', '1',
                   '--results-port', str(port), '--seconds', '.3']
        process = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=8)
        self.assertEqual(process.returncode, 0, process.stderr)
        records = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(records[0]['mode'], 'CSV_rules_peer')
        self.assertEqual(records[1]['expired'], 1)
        key = records[1]['events'][0]['event_id']
        app = self.http.Personalization(db, lambda: self.now, 'test-device')
        self.assertEqual((app.queued(key)[0]['state'], app.queued(key)[0]['attempts']), ('unconfirmed', 0))

    def test_board_scenario_drives_real_rules_and_exports_all_outage_decisions(self):
        from tools import local_routine_v5_scenario as scenario
        from tools.personalization_v5_text import prepared_session
        class Backend:
            fail = False
            def classify(self, text, *, timeout=5):
                if self.fail:
                    raise ConnectionError('synthetic model outage')
                return {'intent': 'needs_help'}
        backend = Backend()
        def factory(*args, **kwargs):
            session, gate = prepared_session(*args, **kwargs)
            gate.retry_seconds = .02
            return session, gate
        with patch.object(scenario, 'SemanticIntentClient', return_value=backend), \
                patch.object(scenario, 'prepared_session', side_effect=factory):
            result = scenario.run_demo(self.root/'scenario', model_url='http://127.0.0.1:1',
                                       model_id='synthetic', stop_backend=lambda: setattr(backend, 'fail', True),
                                       restart_backend=lambda: setattr(backend, 'fail', False))
        self.assertEqual(result['baseline_departure'], '09:00')
        self.assertEqual(result['late_threshold'], '10:30')
        self.assertEqual({c['alert_type'] for c in result['cases']}, set(self.routine.ALERT_TYPES))
        self.assertEqual(result['help_tasks'], 4)
        self.assertEqual([d['source'] for d in result['outage']['policy_decisions']], ['fallback', 'rule'])
        self.assertEqual(result['outage']['classification_attempts'], 1)
        self.assertTrue(all(c['rescan_and_reopen_duplicate'] for c in result['cases']))

    def test_three_rules_cross_actual_peer_and_model_http_implementations(self):
        from src.personalization_v5 import Store
        from tools.personalization_v5_text import Server, prepared_session, post, flush_outbox
        scenarios = (
            ('late_wakeup', replay.at(date(2026, 11, 24), time(8, 30)), '我现在没事，谢谢关心。', 'ok'),
            ('daytime_inactivity', replay.at(date(2026, 11, 24), time(15)), '我现在起不来，帮帮我。', 'needs_help'),
            ('night_bathroom_stay', replay.at(date(2026, 11, 25), time(0)), '我没有说我需要帮助。', 'unclear'),
        )
        class Backend:
            def classify(self, *args, **kwargs):
                raise AssertionError('simulated interface test must not call a real model')
        for kind, now, text, expected in scenarios:
            self.now = now
            scanner = self.setup_app(kind)
            scan = scanner.scan(self.root/('routine-'+kind+'.csv'))
            key = scan['events'][0]['event_id']
            model = Store(self.root/(kind+'-model.sqlite'), 'test-device', 'model', clock=lambda: self.now.timestamp())
            session, _ = prepared_session(model, Backend(), simulate=True, policy='v4-fast')
            server = Server(model, session)
            server.start()
            try:
                with self.http.serve(self.http.RESULTS, self.app.receive) as result_port:
                    self.app.flush(server.http.server_port)
                    self.assertEqual(session.tick(key)['kind'], 'prompt')
                    session.displayed(key)
                    code, value = post(server.url+'/text/v1/answers', {'event_id': key, 'text': text})
                    if expected == 'unclear':
                        self.assertEqual(code, 202)
                        self.assertEqual(session.tick(key)['attempt'], 2)
                        session.displayed(key)
                        code, value = post(server.url+'/text/v1/answers', {'event_id': key, 'text': text})
                    self.assertEqual((code, value['response']), (200, expected))
                    flush_outbox(model, 'http://127.0.0.1:'+str(result_port))
                    self.assertEqual(self.app.summary(key)['current'], value)
                    self.assertEqual(self.app.summary(key)['help_tasks'], int(expected == 'needs_help'))
                    self.assertEqual(post('http://127.0.0.1:'+str(result_port)+self.http.RESULTS, value)[1]['disposition'], 'duplicate')
            finally:
                server.close()
