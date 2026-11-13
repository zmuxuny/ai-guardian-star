"""Worker/ownership regressions with fake bytes, NOT encoded-video validation."""

from dataclasses import replace
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guardian_recording import RecordingManager, SegmentArtifact
from guardian_recording_config import RecordingConfig
from guardian_history import HistoryStore
from guardian_storage import initialize_storage, managed_usage


class FakeStore:
    def __init__(self, config):
        self.config = config
        self.started = []
        self.completed = []
        self.failed = []
        self.gaps = []

    def managed_size_bytes(self):
        return managed_usage(self.config)

    def start_segment(self, *args, **kwargs):
        self.started.append((args, kwargs))

    def finish_segment(self, *args, **kwargs):
        self.completed.append((args, kwargs))

    def fail_segment(self, *args):
        self.failed.append(args)

    def add_gap(self, *args):
        self.gaps.append(args)


class FakeBackend:
    """Writes bytes solely to exercise file/index protocols, never creates MP4."""
    def __init__(self, owner, *, gate=None, fail_write=False, verified=True):
        self.owner = owner
        self.gate = gate
        self.fail_write = fail_write
        self.verified = verified
        self.packets = []
        self.entered = threading.Event()
        self.aborted = False
        owner.append(self)

    def start(self, partial_path, final_path, metadata):
        self.partial = partial_path
        self.final = final_path
        self.metadata = metadata
        self.partial.write_bytes(b"FAKE NOT VIDEO\n")

    def write(self, packet):
        self.entered.set()
        if self.gate is not None:
            self.gate.wait(3)
        if self.fail_write:
            raise OSError("private details must not escape status")
        self.packets.append(packet)
        with self.partial.open("ab") as stream:
            stream.write(packet.data)

    def finish(self):
        self.partial.rename(self.final)
        return SegmentArtifact(self.metadata["relpath"], self.final.stat().st_size,
                               self.verified, 0.0)

    def abort(self):
        self.aborted = True


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = RecordingConfig(enabled=True, data_root=Path(self.temp.name) / "cache",
                                      storage_quota_bytes=10 ** 7, min_free_bytes=1,
                                      encoder="test-only-fake", queue_frames=3,
                                      queue_bytes=24)
        initialize_storage(self.config)
        self.store = FakeStore(self.config)
        self.backends = []
        self.managers = []
        self.gates = []

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        for manager in self.managers:
            manager.stop(timeout=3)
        self.temp.cleanup()

    def manager(self, config=None, **backend_options):
        manager = RecordingManager(config or self.config, self.store,
                                   lambda _: FakeBackend(self.backends, **backend_options))
        self.managers.append(manager)
        self.assertTrue(manager.start())
        return manager

    def wait_until(self, predicate):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.005)
        self.fail("worker did not reach expected state")

    def submit(self, manager, utc=100.0, mono=1.0, data=b"1234"):
        self.assertTrue(manager.submit_frame(data, utc, mono))

    def test_disabled_has_no_storage_thread_or_backend_side_effects(self):
        config = RecordingConfig()
        with patch("threading.Thread", side_effect=AssertionError("thread")), \
                patch("guardian_storage.validate_storage", side_effect=AssertionError("storage")):
            manager = RecordingManager(config, backend_factory=lambda _: self.fail("backend"))
            self.assertFalse(manager.start())
            self.assertFalse(manager.submit_frame(b"x"))
            self.assertTrue(manager.stop())
            self.assertEqual(manager.status()["state"], "disabled")

    def test_enabled_without_backend_fails_closed_before_storage(self):
        manager = RecordingManager(self.config)
        with patch("guardian_storage.validate_storage", side_effect=AssertionError("storage")):
            self.assertFalse(manager.start())
        self.assertEqual(manager.status()["state"], "awaiting_encoder")
        self.assertFalse(manager.status()["worker_alive"])

    def test_enabled_without_store_does_not_create_it(self):
        manager = RecordingManager(self.config, backend_factory=lambda _: None)
        self.assertFalse(manager.start())
        self.assertEqual(manager.status()["state"], "awaiting_storage")

    def test_thread_start_failure_is_reported_and_stop_remains_safe(self):
        manager = RecordingManager(self.config, self.store, lambda _: None)
        with patch("threading.Thread.start", side_effect=RuntimeError("thread unavailable")):
            self.assertFalse(manager.start())
        self.assertEqual(manager.status()["state"], "failed")
        self.assertFalse(manager.status()["worker_alive"])
        self.assertTrue(manager.stop())

    def test_unowned_root_is_not_claimed_by_start(self):
        root = Path(self.temp.name) / "unowned"
        root.mkdir()
        config = replace(self.config, data_root=root)
        manager = RecordingManager(config, FakeStore(config), lambda _: None)
        self.assertFalse(manager.start())
        self.assertEqual(list(root.iterdir()), [])

    def test_buffer_ownership_and_true_capture_timestamps(self):
        gate = threading.Event()
        self.gates.append(gate)
        manager = self.manager(gate=gate)
        frame = bytearray(b"1234")
        self.assertTrue(manager.submit_frame(frame, 123.5, 8.75, frame_id=9))
        frame[:] = b"XXXX"
        self.wait_until(lambda: bool(self.backends) and self.backends[0].entered.is_set())
        gate.set()
        self.assertTrue(manager.stop(3))
        packet = self.backends[0].packets[0]
        self.assertEqual(packet.data, b"1234")
        self.assertEqual((packet.captured_at, packet.monotonic_at, packet.frame_id), (123.5, 8.75, 9))
        self.assertEqual(manager.status()["completed_segments"], 1)
        self.assertEqual(manager.status()["buffered_bytes"], 0)

    def test_frame_and_byte_limits_include_inflight_frame(self):
        gate = threading.Event()
        self.gates.append(gate)
        manager = self.manager(gate=gate)
        self.submit(manager, data=b"12345678")
        self.wait_until(lambda: bool(self.backends) and self.backends[0].entered.is_set())
        self.submit(manager, mono=2, data=b"12345678")
        self.submit(manager, mono=3, data=b"12345678")
        before = time.monotonic()
        self.assertFalse(manager.submit_frame(b"x", 100, 4))
        self.assertLess(time.monotonic() - before, 0.1)
        state = manager.status()
        self.assertEqual((state["buffered_frames"], state["buffered_bytes"]), (3, 24))
        self.assertEqual(state["drop_reasons"]["queue_full"], 1)
        gate.set()
        self.assertTrue(manager.stop(3))
        self.assertTrue(self.store.gaps)

    def test_byte_limit_applies_even_with_available_frame_slots(self):
        gate = threading.Event()
        self.gates.append(gate)
        manager = self.manager(gate=gate)
        self.submit(manager, data=b"a" * 20)
        self.wait_until(lambda: bool(self.backends) and self.backends[0].entered.is_set())
        self.assertFalse(manager.submit_frame(b"a" * 5, 100, 2))
        self.assertEqual(manager.status()["buffered_frames"], 1)

    def test_oversized_invalid_noncontiguous_and_nonfinite_frames_rejected(self):
        manager = self.manager()
        for frame, utc, mono in ((b"x" * 25, 1, 1), (object(), 1, 1),
                                  (memoryview(b"abcdef")[::2], 1, 1),
                                  (b"x", float("nan"), 1), (b"x", 1, float("inf"))):
            self.assertFalse(manager.submit_frame(frame, utc, mono))
        self.assertEqual(manager.status()["dropped_frames"], 5)
        self.assertEqual(manager.status()["buffered_bytes"], 0)

    def test_copy_failure_returns_false_and_releases_reservation(self):
        manager = self.manager()
        class FailingView:
            c_contiguous = True
            nbytes = 4
            itemsize = 1
            format = "B"
            shape = (4,)
            def tobytes(self):
                raise MemoryError("copy failed")
        with patch("guardian_recording.memoryview", return_value=FailingView(), create=True):
            self.assertFalse(manager.submit_frame(b"1234", 100, 1))
        self.assertEqual(manager.status()["drop_reasons"]["copy_failed"], 1)
        self.assertEqual(manager.status()["buffered_bytes"], 0)
        self.submit(manager)

    def test_concurrent_copy_reservation_and_stop_are_bounded(self):
        manager = self.manager(config=replace(self.config, queue_frames=1))
        copying = threading.Event()
        release = threading.Event()
        self.gates.append(release)
        results = []
        class DelayedView:
            c_contiguous = True
            nbytes = 4
            itemsize = 1
            format = "B"
            shape = (4,)
            def tobytes(self):
                copying.set()
                release.wait(3)
                return b"1234"
        with patch("guardian_recording.memoryview", return_value=DelayedView(), create=True):
            submitter = threading.Thread(target=lambda: results.append(manager.submit_frame(b"1234", 100, 1)))
            submitter.start()
            self.assertTrue(copying.wait(1))
            self.assertFalse(manager.submit_frame(b"1234", 100, 2))
            self.assertEqual(manager.status()["copying_frames"], 1)
            self.assertFalse(manager.stop(0.01))
            release.set()
            submitter.join(2)
        self.assertEqual(results, [False])
        self.assertTrue(manager.stop(3))
        self.assertEqual(manager.status()["buffered_bytes"], 0)
        self.assertEqual(manager.status()["buffered_frames"], 0)

    def test_backend_factory_and_finalize_failures_mark_index_failed(self):
        def bad_factory(_):
            raise RuntimeError("backend unavailable")
        manager = RecordingManager(self.config, self.store, bad_factory)
        self.managers.append(manager)
        self.assertTrue(manager.start())
        self.submit(manager)
        self.wait_until(lambda: not manager.status()["worker_alive"])
        self.assertEqual(manager.status()["state"], "failed")
        self.assertEqual(len(self.store.failed), 1)
        self.assertFalse(self.store.completed)

        manager2 = self.manager()
        self.submit(manager2)
        self.wait_until(lambda: manager2.status()["written_frames"] == 1)
        with patch.object(self.backends[-1], "finish", side_effect=OSError("finalize failed")):
            self.assertTrue(manager2.stop(3))
        self.assertEqual(manager2.status()["state"], "failed")
        self.assertEqual(len(self.store.failed), 2)

    def test_real_history_store_matches_backend_finalization_contract(self):
        store = HistoryStore(self.config)
        manager = RecordingManager(self.config, store,
                                   lambda _: FakeBackend(self.backends))
        self.managers.append(manager)
        try:
            self.assertTrue(manager.start())
            self.submit(manager)
            self.assertTrue(manager.stop(3))
            self.assertEqual(manager.status()["state"], "stopped")
            self.assertEqual(manager.status()["completed_segments"], 1)
            segment = self.backends[0].metadata["segment_id"]
            row = store.get_recording(segment)
            self.assertEqual(row["state"], "complete")
            self.assertTrue(row["relpath"].endswith(".mp4"))
        finally:
            manager.stop(3)
            store.close()

    def test_repeated_start_and_stop_are_idempotent(self):
        manager = self.manager()
        worker = manager._worker
        self.assertTrue(manager.start())
        self.assertIs(worker, manager._worker)
        self.submit(manager)
        self.assertTrue(manager.stop(3))
        self.assertTrue(manager.stop(0))
        self.assertFalse(manager.start())
        self.assertEqual(manager.status()["state"], "stopped")
        self.assertEqual(len(self.backends), 1)

    def test_stop_timeout_is_honest_then_worker_can_finish(self):
        gate = threading.Event()
        self.gates.append(gate)
        manager = self.manager(gate=gate)
        self.submit(manager)
        self.wait_until(lambda: bool(self.backends) and self.backends[0].entered.is_set())
        self.assertFalse(manager.stop(0.01))
        self.assertEqual(manager.status()["state"], "stop_timeout")
        self.assertTrue(manager.status()["worker_alive"])
        self.assertFalse(manager.submit_frame(b"x"))
        gate.set()
        self.assertTrue(manager.stop(3))
        self.assertEqual(manager.status()["state"], "stopped")

    def test_encoder_exception_is_visible_and_does_not_escape_caller(self):
        manager = self.manager(fail_write=True)
        self.submit(manager)
        self.wait_until(lambda: not manager.status()["worker_alive"])
        status = manager.status()
        self.assertEqual(status["state"], "failed")
        self.assertEqual(status["error"], "OSError")
        self.assertEqual(status["buffered_bytes"], 0)
        self.assertEqual(len(self.store.failed), 1)
        self.assertTrue(self.backends[0].aborted)
        self.assertFalse(self.store.completed)

    def test_unverified_backend_artifact_never_becomes_complete(self):
        manager = self.manager(verified=False)
        self.submit(manager)
        self.assertTrue(manager.stop(3))
        self.assertEqual(manager.status()["state"], "failed")
        self.assertFalse(self.store.completed)
        self.assertEqual(len(self.store.failed), 1)

    def test_rotation_and_clock_reversal_use_new_segment_not_fake_frames(self):
        manager = self.manager(config=replace(self.config, segment_seconds=2))
        self.submit(manager, utc=100, mono=1)
        self.wait_until(lambda: manager.status()["written_frames"] == 1)
        self.submit(manager, utc=103, mono=4)
        self.wait_until(lambda: manager.status()["written_frames"] == 2)
        self.submit(manager, utc=90, mono=2)
        self.assertTrue(manager.stop(3))
        self.assertEqual(manager.status()["completed_segments"], 3)
        self.assertEqual(sum(len(item.packets) for item in self.backends), 3)
        self.assertTrue(any(item[2] == "capture_clock_discontinuity" for item in self.store.gaps))

    def test_midnight_rotation_in_business_timezone(self):
        manager = self.manager()
        self.submit(manager, utc=86399 - 8 * 3600, mono=1)
        self.wait_until(lambda: manager.status()["written_frames"] == 1)
        self.submit(manager, utc=86400 - 8 * 3600, mono=2)
        self.assertTrue(manager.stop(3))
        self.assertEqual(manager.status()["completed_segments"], 2)
        self.assertIn("1970-01-01", self.store.started[0][0][1])
        self.assertIn("1970-01-02", self.store.started[1][0][1])

    def test_quota_and_minimum_free_fail_without_deleting_old_files(self):
        old = self.config.data_root / "recordings" / "keep.mp4"
        old.write_bytes(b"keep")
        for field, value, expected in (("storage_quota_bytes", 1, "storage_quota_exhausted"),
                                       ("min_free_bytes", 10 ** 30, "storage_minimum_free_reached")):
            config = replace(self.config, **{field: value})
            manager = RecordingManager(config, self.store, lambda _: None)
            self.assertFalse(manager.start())
            self.assertEqual(manager.status()["error"], expected)
            self.assertEqual(old.read_bytes(), b"keep")

    def test_marker_loss_stops_worker_before_next_write(self):
        manager = self.manager()
        self.submit(manager)
        self.wait_until(lambda: manager.status()["written_frames"] == 1)
        (self.config.data_root / ".guardian-recording-root.json").unlink()
        self.submit(manager, mono=2)
        self.wait_until(lambda: not manager.status()["worker_alive"])
        self.assertEqual(manager.status()["state"], "failed")
        self.assertEqual(manager.status()["written_frames"], 1)

    def test_optional_numpy_ownership_and_shape(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest("numpy is optional; buffer tests cover core contract")
        gate = threading.Event()
        self.gates.append(gate)
        manager = self.manager(gate=gate)
        frame = np.arange(12, dtype=np.uint8).reshape((2, 2, 3))
        self.assertTrue(manager.submit_frame(frame, 100, 1))
        frame[:] = 0
        self.wait_until(lambda: bool(self.backends) and self.backends[0].entered.is_set())
        gate.set()
        self.assertTrue(manager.stop(3))
        packet = self.backends[0].packets[0]
        self.assertEqual(packet.shape, (2, 2, 3))
        self.assertEqual(packet.data, bytes(range(12)))


if __name__ == "__main__":
    unittest.main()
