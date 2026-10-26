import os
import json
import sys
import tempfile
import threading
import time
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
        result, pages = self.run_snapshot(
            events=[stale, fresh],
            window_start=self.now - 10 * bridge.DAY,
            window_end=self.now - bridge.DAY)
        self.assertEqual(pages.call_args.args[1], self.retention_start)
        self.assertEqual(pages.call_args.args[2], self.now - bridge.DAY)
        self.assertEqual(result['windowStart'], self.retention_start)
        self.assertEqual(result['windowEnd'], self.now - bridge.DAY)
        self.assertEqual([clip['id'] for clip in result['clips']], ['fresh-event'])

    def test_reverse_degenerate_and_expired_ranges_are_rejected(self):
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'all', self.now, self.now - 1_000)
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'all', self.now - 1_000, self.now - 1_000)
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'unknown')
        with self.assertRaises(ValueError):
            bridge.snapshot(self.now, 'all',
                            self.now - 9 * bridge.DAY, self.now - 8 * bridge.DAY)

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


if __name__ == '__main__':
    unittest.main()