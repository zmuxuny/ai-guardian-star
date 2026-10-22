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
    def test_continuous_is_24_hours_while_events_remain_seven_days(self):
        now = 1_800_000_000
        continuous = RecordingConfig(retention_hours=24)
        events = RecordingConfig()
        self.assertEqual(retention_cutoff(continuous, now), now - 86400)
        self.assertLess(retention_cutoff(events, now), now - 6 * 86400)

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
    def test_boundary_segment_is_not_exposed_and_event_filter_matches(self):
        now = 1_800_000_000_000
        start = now - bridge.DAY
        rows = [
            {'id': 'crosses', 'state': 'complete', 'started_at': bridge._iso(start - 1000),
             'ended_at': bridge._iso(start + 59000)},
            {'id': 'fallclip', 'state': 'complete', 'started_at': bridge._iso(start + 60000),
             'ended_at': bridge._iso(start + 120000)},
            {'id': 'normalclip', 'state': 'complete', 'started_at': bridge._iso(start + 300000),
             'ended_at': bridge._iso(start + 360000)},
        ]
        events = [{'kind': 'fall', 'started_at': bridge._iso(start + 90000),
                   'ended_at': bridge._iso(start + 90000)}]

        def pages(path, _start, _end):
            return events if path.endswith('/events') else rows

        with patch.object(bridge.time, 'time', return_value=now / 1000), \
                patch.object(bridge, '_get_json', return_value={'state': 'running'}), \
                patch.object(bridge, '_pages', side_effect=pages):
            all_result = bridge.snapshot(now, 'all')
            fall_result = bridge.snapshot(now, 'fall')
        self.assertEqual([item['id'] for item in all_result['clips']], ['fallclip', 'normalclip'])
        self.assertEqual([item['id'] for item in fall_result['clips']], ['fallclip'])
        self.assertEqual(all_result['status'], 'recording')
        self.assertTrue(fall_result['wholeSegments'])

    def test_requires_loopback_and_server_side_token(self):
        with patch.dict(os.environ, {'BOARD_RECORDING_BASE_URL': 'http://evil.example',
                                     'BOARD_RECORDING_TOKEN': 'secret'}):
            with self.assertRaises(bridge.BoardRecordingUnavailable):
                bridge.open_media('abc123')


if __name__ == '__main__':
    unittest.main()
