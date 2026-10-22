"""Event-triggered clip cache regressions.

These use a fake backend and a fake clock: they prove the pre-roll ring, the
trigger/deadline logic and the event-to-recording link, NOT real MP4 encoding.
Real encoder verification lives in the board record under docs/修改记录/.
"""

from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guardian_event_cache import EventClipCache
from guardian_history import HistoryStore
from guardian_recording import SegmentArtifact
from guardian_recording_config import RecordingConfig
from guardian_storage import initialize_storage


class FakeClock:
    """Deterministic UTC/monotonic pair; advance() simulates elapsed time."""

    def __init__(self, utc=1_700_000_000.0, mono=1000.0):
        self.utc = utc
        self.mono = mono
        self._lock = threading.Lock()

    def now(self):
        with self._lock:
            return self.utc

    def monotonic(self):
        with self._lock:
            return self.mono

    def advance(self, seconds):
        with self._lock:
            self.utc += seconds
            self.mono += seconds


class FakeBackend:
    def __init__(self, owner):
        self.owner = owner
        self.packets = []
        owner.append(self)

    def start(self, partial_path, final_path, metadata):
        self.partial, self.final, self.metadata = partial_path, final_path, metadata
        self.partial.write_bytes(b"FAKE NOT VIDEO\n")

    def write(self, packet):
        self.packets.append(packet)
        with self.partial.open("ab") as stream:
            stream.write(packet.data)

    def finish(self):
        self.partial.rename(self.final)
        return SegmentArtifact(self.metadata["relpath"], self.final.stat().st_size, True, 0.0)

    def abort(self):
        pass


class EventClipCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = RecordingConfig(
            enabled=True, data_root=Path(self.temp.name) / "clips",
            storage_quota_bytes=10 ** 7, min_free_bytes=1,
            encoder="test-only-fake", record_fps=10.0,
            pre_roll_seconds=2, post_roll_seconds=1, event_clip_max_seconds=10,
            cache_bytes=1024 * 1024)
        initialize_storage(self.config)
        self.store = HistoryStore(self.config)
        self.clock = FakeClock()
        self.backends = []
        self.cache = None

    def tearDown(self):
        if self.cache is not None:
            self.cache.stop(timeout=5)
        self.store.close()
        self.temp.cleanup()

    def start_cache(self, factory=None):
        self.cache = EventClipCache(
            self.config, self.store,
            factory or (lambda _: FakeBackend(self.backends)),
            clock=self.clock.now, monotonic=self.clock.monotonic)
        self.assertTrue(self.cache.start())
        return self.cache

    def feed(self, count, start_index=0, frame=None):
        frame = np.zeros((48, 64, 3), dtype=np.uint8) if frame is None else frame
        for index in range(start_index, start_index + count):
            self.clock.advance(0.1)
            accepted = self.cache.submit_frame(
                frame, captured_at=self.clock.now(),
                monotonic_at=self.clock.monotonic(), frame_id=index)
            self.assertTrue(accepted)

    def wait_until(self, predicate, seconds=5.0):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if predicate():
                return True
            time.sleep(0.01)
        return False

    def test_idle_ring_is_bounded_by_frames(self):
        self.start_cache()
        self.feed(100)
        status = self.cache.status()
        self.assertLessEqual(status["pre_roll_frames_cached"], 22)
        self.assertGreater(status["pre_roll_frames_cached"], 0)
        self.assertGreater(status["dropped_frames"], 0)

    def test_trigger_records_pre_roll_then_post_roll_and_links_event(self):
        self.start_cache()
        self.feed(20)
        trigger_at = self.clock.now()
        result = self.cache.trigger("fall", payload={"score": 0.9})
        self.assertFalse(result["extended"])
        self.assertGreater(result["pre_roll_frames"], 0)
        self.feed(10, start_index=100)
        self.clock.advance(1.5)
        self.assertTrue(self.wait_until(lambda: self.cache.status()["completed_clips"] == 1))
        status = self.cache.status()
        self.assertTrue(status["last_clip"]["finalized"])
        self.assertEqual(status["last_clip"]["linked_events"], 1)
        linked = self.store.list_event_recordings(result["event_id"])
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["state"], "complete")
        backend = self.backends[0]
        self.assertGreaterEqual(len(backend.packets), 1)
        self.assertLessEqual(backend.packets[0].captured_at, trigger_at)
        self.assertLessEqual(backend.packets[-1].captured_at, self.clock.now())

    def test_second_trigger_extends_one_clip_with_two_events(self):
        self.start_cache()
        self.feed(10)
        first = self.cache.trigger("fall")
        self.clock.advance(0.5)
        second = self.cache.trigger("stranger")
        self.assertTrue(second["extended"])
        self.assertEqual(second["event_count"], 2)
        self.feed(10, start_index=200)
        self.clock.advance(1.6)
        self.assertTrue(self.wait_until(lambda: self.cache.status()["completed_clips"] == 1))
        self.assertEqual(self.cache.status()["last_clip"]["linked_events"], 2)
        self.assertEqual(len(self.store.list_event_recordings(first["event_id"])), 1)
        self.assertEqual(len(self.store.list_event_recordings(second["event_id"])), 1)
        self.assertEqual(len(self.backends), 1)

    def test_frame_shape_survives_the_ring_copy(self):
        self.start_cache()
        self.feed(5)
        self.cache.trigger("fall")
        self.feed(3, start_index=300)
        self.clock.advance(1.5)
        self.assertTrue(self.wait_until(lambda: self.cache.status()["completed_clips"] == 1))
        self.assertEqual(self.backends[0].packets[0].shape, (48, 64, 3))

    def test_existing_event_can_be_linked_without_creating_another(self):
        self.start_cache()
        self.feed(3)
        event_id = self.store.add_event("sit", self.clock.now())
        result = self.cache.trigger(event_id=event_id)
        self.assertEqual(result["event_id"], event_id)
        self.feed(3, start_index=400)
        self.clock.advance(1.5)
        self.assertTrue(self.wait_until(lambda: self.cache.status()["completed_clips"] == 1))
        self.assertEqual(len(self.store.list_events()), 1)

    def test_disabled_config_never_captures(self):
        disabled = RecordingConfig()
        cache = EventClipCache(disabled, None, None)
        self.assertFalse(cache.start())
        self.assertFalse(cache.submit_frame(b"\x00" * 16))
        self.assertIsNone(cache.trigger("fall"))
        self.assertEqual(cache.status()["state"], "stopped")
        self.assertEqual(cache.status()["accepted_frames"], 0)

    def test_legacy_database_gains_link_table_in_place(self):
        """An existing v1 database must not need a rebuild to store links."""
        db_path = self.config.data_root / "db" / "history.db"
        self.store.close()
        db = sqlite3.connect(str(db_path))
        db.execute("DROP TABLE IF EXISTS event_recordings")
        db.commit()
        db.close()
        reopened = HistoryStore(self.config)
        try:
            probe = sqlite3.connect(str(db_path))
            try:
                tables = probe.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            finally:
                probe.close()
            self.assertIn(("event_recordings",), tables)
        finally:
            reopened.close()


if __name__ == "__main__":
    unittest.main()
