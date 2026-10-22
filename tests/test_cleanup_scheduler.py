"""Retention scheduler regressions: trust gate, lease protection, real deletion."""

from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guardian_cleanup import CleanupScheduler, system_clock_trusted
from guardian_history import HistoryStore
from guardian_recording_config import RecordingConfig
from guardian_storage import initialize_storage

OLD_STARTED_AT = time.time() - 10 * 24 * 3600.0  # 超过七天保留期


class CleanupSchedulerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = RecordingConfig(
            enabled=True, data_root=Path(self.temp.name) / "managed",
            storage_quota_bytes=64 * 1024 * 1024, min_free_bytes=1)
        initialize_storage(self.config)
        self.store = HistoryStore(self.config)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def make_expired_recording(self, recording_id="old-1"):
        relpath = f"recordings/2026-10-01/{recording_id}.mp4"
        self.store.start_segment(recording_id, relpath, OLD_STARTED_AT)
        media = self.config.data_root / relpath
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"OLD CLIP")
        self.store.finish_segment(recording_id, OLD_STARTED_AT + 5,
                                  media.stat().st_size, relpath=relpath,
                                  duration_seconds=5.0)
        # 直接把时间戳改到七天以前，模拟"真实跑到第八天"
        with self.store._write_lock, self.store._connection() as db:
            db.execute("UPDATE recordings SET started_at=?, ended_at=? WHERE id=?",
                       (OLD_STARTED_AT, OLD_STARTED_AT + 5, recording_id))
        return media

    def test_expired_media_is_deleted_when_clock_is_trusted(self):
        media = self.make_expired_recording()
        scheduler = CleanupScheduler(self.store, 60, trusted_probe=lambda: True)
        summary = scheduler.run_once()
        self.assertEqual(summary["deleted"], 1)
        self.assertFalse(media.exists())
        self.assertIsNone(self.store.get_recording("old-1"))
        self.assertTrue(scheduler.status()["last_summary"])

    def test_nothing_is_deleted_when_clock_is_untrusted(self):
        media = self.make_expired_recording()
        scheduler = CleanupScheduler(self.store, 60, trusted_probe=lambda: False)
        summary = scheduler.run_once()
        self.assertEqual(summary.get("skipped"), "untrusted_time")
        self.assertTrue(media.exists())
        self.assertIsNotNone(self.store.get_recording("old-1"))

    def test_download_lease_protects_expired_media_from_sweep(self):
        media = self.make_expired_recording()
        self.store.lease_recording("old-1", 3600)
        scheduler = CleanupScheduler(self.store, 60, trusted_probe=lambda: True)
        summary = scheduler.run_once()
        self.assertEqual(summary["deleted"], 0)
        self.assertTrue(media.exists())
        self.assertIsNotNone(self.store.get_recording("old-1"))

    def test_start_and_stop_cycle(self):
        scheduler = CleanupScheduler(self.store, 60, trusted_probe=lambda: False)
        self.assertTrue(scheduler.start())
        self.addCleanup(scheduler.stop, 5)
        self.assertTrue(scheduler.status()["worker_alive"])
        self.assertTrue(scheduler.stop())
        self.assertFalse(scheduler.status()["worker_alive"])

    def test_trust_probe_requires_plausible_year_and_ntp(self):
        self.assertFalse(system_clock_trusted(1.0))  # epoch 附近不可信
        # 不 mock timedatectl：本机结果不确定，只验证不抛异常且返回布尔
        self.assertIsInstance(system_clock_trusted(), bool)


if __name__ == "__main__":
    unittest.main()
