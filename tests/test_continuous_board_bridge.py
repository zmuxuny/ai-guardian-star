import os
import json
import sys
import tempfile
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


if __name__ == '__main__':
    unittest.main()
