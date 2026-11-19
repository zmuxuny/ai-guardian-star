"""A late camera frame must not deadlock after event-cache shutdown."""
import sys
from pathlib import Path
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from guardian_event_cache import EventClipCache
from guardian_recording_config import RecordingConfig


class EventCacheShutdownTests(unittest.TestCase):
    def test_late_frame_is_rejected_after_stop_and_status_remains_available(self):
        config = RecordingConfig(enabled=True, data_root=Path('unused-shutdown-test').resolve(),
                                 storage_quota_bytes=1024 * 1024, min_free_bytes=1)
        cache = EventClipCache(config, object(), lambda _: None)
        self.assertTrue(cache.start())
        self.assertTrue(cache.stop(timeout=1))
        result = []
        def late_frame():
            result.append(cache.submit_frame(b'late-camera-frame'))
            result.append(cache.status())
        worker = threading.Thread(target=late_frame, daemon=True)
        worker.start()
        worker.join(timeout=1)
        self.assertFalse(worker.is_alive(), 'late frame deadlocked after stop')
        self.assertEqual(result[0], False)
        self.assertEqual(result[1]['drop_reasons']['not_running'], 1)


if __name__ == '__main__':
    unittest.main()
