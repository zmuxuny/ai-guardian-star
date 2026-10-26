import os
import json
import importlib.util
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

import board_recording_bridge as bridge
from guardian_continuous import ContinuousCaptureSink
from guardian_recording_config import RecordingConfig
from guardian_storage import retention_cutoff


def load_recording_api_for_test():
    """Load recording_api without requiring the production Flask package on Windows."""
    flask = types.ModuleType('flask')
    for name in ('request', 'jsonify', 'g', 'send_file', 'Response', 'stream_with_context'):
        setattr(flask, name, object())
    mqtt_access = types.ModuleType('mqtt_access')
    mqtt_access.allowed_users = lambda _path: set()
    module_name = 'recording_api_under_test'
    spec = importlib.util.spec_from_file_location(module_name, ROOT / 'recording_api.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'flask': flask, 'mqtt_access': mqtt_access}):
        spec.loader.exec_module(module)
    return module


class CaptureSinkTests(unittest.TestCase):
    def test_uses_one_camera_stream_at_recording_rate(self):
        class Manager:
            def __init__(self):
                self.frames = []

            def submit_frame(self, frame, **kwargs):
                self.frames.append((frame, kwargs))
                return True

        class Frame:
            shape = (480, 640, 3)

        manager = Manager()
        sink = ContinuousCaptureSink(manager, fps=8)
        self.assertTrue(sink(Frame(), 1000, 10.0))
        self.assertFalse(sink(Frame(), 1000.02, 10.02))
        self.assertTrue(sink(Frame(), 1000.13, 10.13))
        self.assertEqual(len(manager.frames), 2)
        self.assertEqual(manager.frames[1][1]['captured_at'], 1000.13)


class RollingRetentionTests(unittest.TestCase):
    def test_continuous_is_24_hours_while_events_expire_after_168_hours(self):
        now = 1_800_000_000
        continuous = RecordingConfig(retention_hours=24)
        events = RecordingConfig(retention_hours=168)
        self.assertEqual(retention_cutoff(continuous, now), now - 86400)
        self.assertEqual(retention_cutoff(events, now), now - 7 * 86400)

    def test_continuous_config_is_independent_of_event_config(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'continuous.json'
            path.write_text(json.dumps({'enabled': True, 'data_root': str(Path(directory) / 'video'),
                                        'storage_quota_bytes': 10_000_000,
                                        'min_free_bytes': 1_000_000,
                                        'retention_hours': 24, 'encoder': 'libx264'}),
                            encoding='utf-8')
            environ = {'AI_GUARDIAN_CONTINUOUS_CONFIG': str(path)}
            self.assertFalse(RecordingConfig.from_env(environ).enabled)
            self.assertTrue(RecordingConfig.from_env(
                environ, config_env_var='AI_GUARDIAN_CONTINUOUS_CONFIG').enabled)


class BoardBridgeTests(unittest.TestCase):
    def test_lists_event_summary_and_only_complete_clip_is_downloadable(self):
        now = 1_800_000_000_000
        start = now - bridge.RETENTION_MS
        events = [
            {'id': 'fall-event', 'kind': 'fall', 'started_at': bridge._iso(start + 60000),
             'ended_at': bridge._iso(start + 61000)},
            {'id': 'sit-event', 'kind': 'sit', 'started_at': bridge._iso(start + 120000),
             'ended_at': None},
        ]

        def get_json(path, _query=None):
            if path == '/api/history/status':
                return {'state': 'running'}
            if path.endswith('fall-event'):
                return {'recordings': [{'id': 'fall-video', 'state': 'complete'}]}
            if path.endswith('sit-event'):
                return {'recordings': [{'id': 'sit-video', 'state': 'recording'}]}
            raise AssertionError(path)

        with patch.object(bridge.time, 'time', return_value=now / 1000), \
                patch.object(bridge, '_get_json', side_effect=get_json), \
                patch.object(bridge, '_pages', return_value=iter(events)):
            result = bridge.snapshot(now, 'all')
        self.assertEqual([item['id'] for item in result['clips']], ['sit-event', 'fall-event'])
        self.assertEqual(result['clips'][0]['eventType'], 'sedentary')
        self.assertFalse(result['clips'][0]['downloadable'])
        self.assertEqual(result['clips'][1]['segmentId'], 'fall-video')
        self.assertTrue(result['clips'][1]['downloadable'])
        self.assertEqual(result['windowStart'], now - bridge.RETENTION_MS)
        self.assertEqual(result['status'], 'recording')
        self.assertFalse(result['wholeSegments'])

    def test_event_filter_is_forwarded_to_board(self):
        now = 1_800_000_000_000
        with patch.object(bridge.time, 'time', return_value=now / 1000), \
                patch.object(bridge, '_get_json', return_value={'state': 'running'}), \
                patch.object(bridge, '_pages', return_value=iter([])) as pages:
            bridge.snapshot(now, 'stranger')
        self.assertEqual(pages.call_args.args[0], '/api/history/events')
        self.assertEqual(pages.call_args.args[3], {'kind': 'stranger'})

    def test_requires_loopback_and_server_side_token(self):
        with patch.dict(os.environ, {'BOARD_RECORDING_BASE_URL': 'http://evil.example',
                                     'BOARD_RECORDING_TOKEN': 'secret'}):
            with self.assertRaises(bridge.BoardRecordingUnavailable):
                bridge.open_media('abc123')


class BoundedDayQueryTests(unittest.TestCase):
    """Assert on snapshot() behaviour, never only on mock call counts."""

    now = 1_800_000_000_000

    @property
    def retention_start(self):
        return self.now - bridge.RETENTION_MS

    def event(self, event_id, started_at, kind='fall', ended_at=None):
        return {'id': event_id, 'kind': kind, 'started_at': bridge._iso(started_at),
                'ended_at': bridge._iso(ended_at) if ended_at is not None else None}

    def run_snapshot(self, events=(), kind='all', window_start=None, window_end=None,
                     get_json=None):
        if get_json is None:
            def get_json(path, _query=None):
                if path == '/api/history/status':
                    return {'state': 'running'}
                return {'recordings': []}
        with patch.object(bridge.time, 'time', return_value=self.now / 1000), \
                patch.object(bridge, '_get_json', side_effect=get_json), \
                patch.object(bridge, '_pages', return_value=iter(list(events))) as pages:
            result = bridge.snapshot(self.now, kind, window_start, window_end)
        return result, pages

    def test_requested_day_window_reaches_board_event_query(self):
        window_start = self.now - 5 * 3_600_000
        window_end = self.now - 3_600_000
        result, pages = self.run_snapshot(window_start=window_start, window_end=window_end)
        self.assertEqual(pages.call_args.args[0], '/api/history/events')
        self.assertEqual(pages.call_args.args[1], window_start)
        self.assertEqual(pages.call_args.args[2], window_end)
        self.assertEqual(result['windowStart'], window_start)
        self.assertEqual(result['windowEnd'], window_end)
        self.assertEqual(result['asOf'], self.now)

    def test_window_is_clipped_to_rolling_retention_and_drops_stale_events(self):
        stale = self.event('stale-event', self.retention_start - 60_000)
        fresh = self.event('fresh-event', self.retention_start + 60_000)
        after_requested_day = self.event('next-day-event', self.now - 60_000)
        result, pages = self.run_snapshot(
            events=[stale, fresh, after_requested_day],
            window_start=self.now - 10 * bridge.DAY,
            window_end=self.now - bridge.DAY)
        self.assertEqual(pages.call_args.args[1], self.retention_start)
        self.assertEqual(pages.call_args.args[2], self.now - bridge.DAY)
        self.assertEqual(result['windowStart'], self.retention_start)
        self.assertEqual(result['windowEnd'], self.now - bridge.DAY)
        self.assertEqual([clip['id'] for clip in result['clips']], ['fresh-event'])

    def test_reverse_and_degenerate_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'all', self.now, self.now - 1_000)
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'all', self.now - 1_000, self.now - 1_000)
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'unknown')

    def test_future_and_post_as_of_windows_are_rejected(self):
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'all', self.now + 1_000, self.now + 2_000)
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now - bridge.DAY, 'all',
                            self.now - bridge.DAY + 1_000, self.now - bridge.DAY + 2_000)

    def test_well_formed_window_that_aged_out_returns_an_empty_snapshot(self):
        result, pages = self.run_snapshot(
            window_start=self.now - 9 * bridge.DAY,
            window_end=self.now - 8 * bridge.DAY)
        self.assertEqual(result['clips'], [])
        self.assertEqual(result['eventCount'], 0)
        self.assertEqual(result['windowStart'], self.retention_start)
        self.assertEqual(result['windowEnd'], self.retention_start)
        pages.assert_not_called()

    def test_event_details_are_fetched_concurrently(self):
        events = [self.event('event-%d' % index, self.now - (index + 1) * 60_000)
                  for index in range(6)]
        lock = threading.Lock()
        state = {'active': 0, 'maxActive': 0}

        def get_json(path, _query=None):
            if path == '/api/history/status':
                return {'state': 'running'}
            with lock:
                state['active'] += 1
                state['maxActive'] = max(state['maxActive'], state['active'])
            time.sleep(0.08)
            with lock:
                state['active'] -= 1
            return {'recordings': [{'id': 'segment-' + path.rsplit('/', 1)[-1],
                                    'state': 'complete'}]}

        result, _pages_mock = self.run_snapshot(
            events=events, window_start=self.now - 3_600_000, window_end=self.now,
            get_json=get_json)
        self.assertGreater(state['maxActive'], 1)
        self.assertEqual(len(result['clips']), 6)
        self.assertTrue(all(clip['downloadable'] for clip in result['clips']))

    def test_detail_concurrency_has_a_fixed_upper_bound(self):
        events = [self.event('event-%d' % index, self.now - (index + 1) * 60_000)
                  for index in range(12)]
        lock = threading.Lock()
        state = {'active': 0, 'maxActive': 0}

        def get_json(path, _query=None):
            if path == '/api/history/status':
                return {'state': 'running'}
            with lock:
                state['active'] += 1
                state['maxActive'] = max(state['maxActive'], state['active'])
            time.sleep(0.05)
            with lock:
                state['active'] -= 1
            return {'recordings': []}

        result, _pages_mock = self.run_snapshot(
            events=events, window_start=self.now - 3_600_000, window_end=self.now,
            get_json=get_json)
        self.assertGreater(state['maxActive'], 1)
        self.assertLessEqual(state['maxActive'], 8)
        self.assertEqual(len(result['clips']), 12)

    def test_clips_stay_newest_first_when_details_finish_out_of_order(self):
        events = [self.event('event-%d' % index, self.now - (10 - index) * 60_000)
                  for index in range(6)]

        def get_json(path, _query=None):
            if path == '/api/history/status':
                return {'state': 'running'}
            index = int(path.rsplit('-', 1)[-1])
            time.sleep(0.01 * (5 - index))
            return {'recordings': []}

        result, _pages_mock = self.run_snapshot(
            events=events, window_start=self.now - 3_600_000, window_end=self.now,
            get_json=get_json)
        self.assertEqual([clip['id'] for clip in result['clips']],
                         ['event-5', 'event-4', 'event-3', 'event-2', 'event-1', 'event-0'])
        starts = [clip['startTime'] for clip in result['clips']]
        self.assertEqual(starts, sorted(starts, reverse=True))

    def test_one_failed_detail_does_not_drop_other_events(self):
        events = [self.event('event-a', self.now - 180_000),
                  self.event('event-b', self.now - 120_000),
                  self.event('event-c', self.now - 60_000)]

        def get_json(path, _query=None):
            if path == '/api/history/status':
                return {'state': 'running'}
            if path.endswith('event-b'):
                raise bridge.BoardRecordingUnavailable('detail down')
            return {'recordings': [{'id': 'segment-' + path.rsplit('/', 1)[-1],
                                    'state': 'complete'}]}

        result, _pages_mock = self.run_snapshot(
            events=events, window_start=self.now - 3_600_000, window_end=self.now,
            get_json=get_json)
        self.assertEqual([clip['id'] for clip in result['clips']], ['event-c', 'event-a'])
        self.assertTrue(all(clip['downloadable'] for clip in result['clips']))

    def test_malformed_events_are_skipped_without_failing_the_day(self):
        events = [self.event('event-ok', self.now - 60_000),
                  {'id': 'event-no-start', 'kind': 'fall'},
                  {'id': 'event-bad-kind', 'kind': 'noise',
                   'started_at': bridge._iso(self.now - 120_000)},
                  {'id': '../escape', 'kind': 'fall',
                   'started_at': bridge._iso(self.now - 180_000)}]
        result, _pages_mock = self.run_snapshot(
            events=events, window_start=self.now - 3_600_000, window_end=self.now)
        self.assertEqual([clip['id'] for clip in result['clips']], ['event-ok'])

    def test_kind_filter_and_event_semantics_survive_day_windows(self):
        events = [self.event('sit-event', self.now - 60_000, kind='sit'),
                  self.event('stranger-event', self.now - 120_000, kind='stranger'),
                  self.event('fall-event', self.now - 180_000, kind='fall',
                             ended_at=self.now - 170_000)]

        def get_json(path, _query=None):
            if path == '/api/history/status':
                return {'state': 'running'}
            return {'recordings': [{'id': 'segment-' + path.rsplit('/', 1)[-1],
                                    'state': 'complete'}]}

        result, pages = self.run_snapshot(
            events=events, kind='sedentary',
            window_start=self.now - 3_600_000, window_end=self.now,
            get_json=get_json)
        self.assertEqual(pages.call_args.args[3], {'kind': 'sit'})
        by_id = {clip['id']: clip for clip in result['clips']}
        self.assertEqual(by_id['sit-event']['eventType'], 'sedentary')
        self.assertEqual(by_id['stranger-event']['eventType'], 'stranger')
        self.assertEqual(by_id['fall-event']['eventType'], 'fall')
        self.assertFalse(by_id['fall-event']['endUnconfirmed'])
        self.assertTrue(by_id['sit-event']['endUnconfirmed'])
        self.assertTrue(all(clip['downloadable'] for clip in result['clips']))
        _result_all, pages_all = self.run_snapshot(
            events=[], kind='all',
            window_start=self.now - 3_600_000, window_end=self.now)
        self.assertEqual(pages_all.call_args.args[3], {})


class RecordingApiFallbackTests(unittest.TestCase):
    def setUp(self):
        self.api = load_recording_api_for_test()
        self.now = 1_800_000_000_000

    def fallback_result(self):
        return {'success': True, 'asOf': self.now,
                'windowStart': self.now - bridge.DAY, 'windowEnd': self.now,
                'status': 'recording',
                'clips': [
                    {'id': 'older', 'startTime': self.now - 3_600_000},
                    {'id': 'inside', 'startTime': self.now - 1_800_000},
                    {'id': 'later', 'startTime': self.now - 60_000},
                ],
                'eventCount': 3, 'wholeSegments': False}

    def test_local_fallback_uses_the_intersection_of_store_and_requested_windows(self):
        with patch.object(self.api.board_bridge, 'configured', return_value=False), \
                patch.object(self.api, 'snapshot', return_value=self.fallback_result()), \
                patch.object(self.api.time, 'time', return_value=self.now / 1000):
            result = self.api._snapshot(
                self.now, 'all', self.now - 2_000_000, self.now - 1_000_000)
        self.assertEqual([clip['id'] for clip in result['clips']], ['inside'])
        self.assertEqual(result['windowStart'], self.now - 2_000_000)
        self.assertEqual(result['windowEnd'], self.now - 1_000_000)
        self.assertEqual(result['eventCount'], 1)

    def test_local_fallback_returns_empty_when_a_valid_window_has_aged_out(self):
        with patch.object(self.api.board_bridge, 'configured', return_value=False), \
                patch.object(self.api, 'snapshot', return_value=self.fallback_result()), \
                patch.object(self.api.time, 'time', return_value=self.now / 1000):
            result = self.api._snapshot(
                self.now, 'all', self.now - 3 * bridge.DAY, self.now - 2 * bridge.DAY)
        self.assertEqual(result['clips'], [])
        self.assertEqual(result['eventCount'], 0)
        self.assertEqual(result['windowStart'], self.now - bridge.DAY)
        self.assertEqual(result['windowEnd'], self.now - bridge.DAY)

    def test_local_fallback_rejects_future_and_post_as_of_windows(self):
        with patch.object(self.api.board_bridge, 'configured', return_value=False), \
                patch.object(self.api, 'snapshot', return_value=self.fallback_result()), \
                patch.object(self.api.time, 'time', return_value=self.now / 1000):
            with self.assertRaises(ValueError):
                self.api._snapshot(
                    self.now, 'all', self.now + 1_000, self.now + 2_000)
            with self.assertRaises(ValueError):
                self.api._snapshot(
                    self.now - 3_600_000, 'all', self.now - 3_599_000, self.now - 3_598_000)


class RecordingApiStatusTests(unittest.TestCase):
    class FakeApp:
        def __init__(self):
            self.routes = {}

        def post(self, path):
            def decorator(function):
                self.routes[path] = function
                return function
            return decorator

    def setUp(self):
        self.api = load_recording_api_for_test()
        self.app = self.FakeApp()
        self.api.request = types.SimpleNamespace(get_json=lambda silent=True: {})
        self.api.g = types.SimpleNamespace(current_username='allowed-user')
        class FakeJsonResponse(dict):
            def __init__(self, values):
                super().__init__(values)
                self.headers = {}
        self.api.jsonify = lambda *args, **values: FakeJsonResponse(args[0] if args else values)
        self.api.allowed_users = lambda _path: {'allowed-user'}
        self.api.register_recording_routes(self.app, lambda function: function)

    def call_media(self, data):
        self.api.request.get_json = lambda silent=True: data
        return self.app.routes['/api/recordings/media']()

    def call_query(self, data):
        self.api.request.get_json = lambda silent=True: data
        return self.app.routes['/api/recordings/query']()

    def test_query_allows_an_explicit_aged_out_window_to_return_empty(self):
        now = 1_800_000_000_000
        empty = {'success': True, 'asOf': now - 8 * bridge.DAY,
                 'windowStart': now - 7 * bridge.DAY,
                 'windowEnd': now - 7 * bridge.DAY,
                 'clips': [], 'eventCount': 0}
        with patch.object(self.api.time, 'time', return_value=now / 1000), \
                patch.object(self.api, '_snapshot', return_value=empty) as snapshot_call:
            response = self.call_query({
                'asOf': now - 8 * bridge.DAY, 'filter': 'all',
                'windowStart': now - 9 * bridge.DAY,
                'windowEnd': now - 8 * bridge.DAY})
        self.assertEqual(response, empty)
        snapshot_call.assert_called_once()

    def test_query_rejects_future_window_through_board_and_local_paths(self):
        now = 1_800_000_000_000
        data = {'asOf': now, 'filter': 'all',
                'windowStart': now + 1_000, 'windowEnd': now + 2_000}
        fallback = {'success': True, 'asOf': now,
                    'windowStart': now - bridge.DAY, 'windowEnd': now,
                    'status': 'recording', 'clips': [], 'eventCount': 0}
        for configured in (True, False):
            with self.subTest(configured=configured), \
                    patch.object(self.api.board_bridge, 'configured', return_value=configured), \
                    patch.object(self.api.time, 'time', return_value=now / 1000), \
                    patch.object(bridge.time, 'time', return_value=now / 1000), \
                    patch.object(self.api, 'snapshot', return_value=fallback):
                body, status = self.call_query(data)
            self.assertEqual(status, 400)
            self.assertEqual(body['message'], '录像时间范围无效')

    def test_media_returns_404_for_expired_window_through_board_and_local_paths(self):
        now = 1_800_000_000_000
        data = {'asOf': now, 'filter': 'all', 'clipId': 'event-a',
                'windowStart': now - 9 * bridge.DAY,
                'windowEnd': now - 8 * bridge.DAY}
        fallback = {'success': True, 'asOf': now,
                    'windowStart': now - bridge.DAY, 'windowEnd': now,
                    'status': 'recording', 'clips': [], 'eventCount': 0}
        for configured in (True, False):
            with self.subTest(configured=configured), \
                    patch.object(self.api.board_bridge, 'configured', return_value=configured), \
                    patch.object(self.api.time, 'time', return_value=now / 1000), \
                    patch.object(bridge.time, 'time', return_value=now / 1000), \
                    patch.object(self.api, 'snapshot', return_value=fallback):
                body, status = self.call_media(data)
            self.assertEqual(status, 404)
            self.assertIn('已过期', body['message'])

    def test_media_rejects_a_malformed_window_with_400(self):
        body, status = self.call_media({
            'asOf': 1_800_000_000_000, 'filter': 'all', 'clipId': 'event-a',
            'windowStart': 2000, 'windowEnd': 1000})
        self.assertEqual(status, 400)
        self.assertEqual(body['message'], '请求格式无效')

    def test_media_returns_404_when_a_valid_window_has_naturally_expired(self):
        empty = {'success': True, 'clips': [], 'eventCount': 0}
        with patch.object(self.api, '_snapshot', return_value=empty):
            body, status = self.call_media({
                'asOf': 1_800_000_000_000, 'filter': 'all', 'clipId': 'event-a',
                'windowStart': 1000, 'windowEnd': 2000})
        self.assertEqual(status, 404)
        self.assertIn('已过期', body['message'])

    def test_media_keeps_429_for_a_clip_that_is_still_being_generated(self):
        pending = {'success': True, 'clips': [
            {'id': 'event-a', 'segmentId': '', 'downloadable': False}], 'eventCount': 1}
        with patch.object(self.api, '_snapshot', return_value=pending):
            body, status = self.call_media({
                'asOf': 1_800_000_000_000, 'filter': 'all', 'clipId': 'event-a',
                'windowStart': 1000, 'windowEnd': 2000})
        self.assertEqual(status, 429)
        self.assertIn('正在生成', body['message'])

    def test_media_keeps_503_for_an_unavailable_board_bridge(self):
        with patch.object(self.api, '_snapshot',
                          side_effect=bridge.BoardRecordingUnavailable('down')):
            body, status = self.call_media({
                'asOf': 1_800_000_000_000, 'filter': 'all', 'clipId': 'event-a',
                'windowStart': 1000, 'windowEnd': 2000})
        self.assertEqual(status, 503)
        self.assertIn('开发板', body['message'])


if __name__ == '__main__':
    unittest.main()
