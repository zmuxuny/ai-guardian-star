"""Real temporary SQLite/filesystem tests; no cameras or production deletion."""
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guardian_recording_config import RecordingConfig
from guardian_history import HistoryStore
from guardian_storage import (MARKER_NAME, SHANGHAI, cleanup_expired,
                              initialize_storage, managed_usage, safe_managed_path,
                              storage_status, validate_storage)


def ts(value):
    return datetime.fromisoformat(value).replace(tzinfo=SHANGHAI).timestamp()


class ConfigurationTests(unittest.TestCase):
    def test_disabled_does_not_touch_any_storage(self):
        config = RecordingConfig()
        with patch("guardian_storage.Path.stat", side_effect=AssertionError("filesystem touched")):
            store = HistoryStore(config)
            self.assertEqual(store.list_recordings(), [])
            self.assertEqual(store.managed_size_bytes(), 0)
            self.assertEqual(cleanup_expired(store)["skipped"], "disabled")
            self.assertEqual(storage_status(config)["state"], "disabled")
            store.close()

    def test_opt_in_requires_explicit_capacity_and_strict_types(self):
        for values in ({"enabled": True}, {"enabled": "false"},
                       {"record_fps": True}, {"bitrate_mbps": float("nan")},
                       {"queue_bytes": -1}, {"data_root": "relative/path"},
                       {"retention_days": 8}, {"min_free_bytes": True},
                       {"journal_mode": "WAL"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                RecordingConfig(**values)

    def test_file_config_secret_is_env_only_and_not_in_repr(self):
        with tempfile.TemporaryDirectory() as tmp:
            filename = Path(tmp) / "config.json"
            filename.write_text('{"enabled":false}', encoding="utf-8")
            config = RecordingConfig.from_env({"AI_GUARDIAN_RECORDING_CONFIG": str(filename),
                                               "AI_GUARDIAN_HISTORY_TOKEN": "private-test-token"})
            self.assertEqual(config.history_token, "private-test-token")
            self.assertNotIn("private-test-token", repr(config))
            filename.write_text('{"history_token":"do-not-store"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                RecordingConfig.from_env({"AI_GUARDIAN_RECORDING_CONFIG": str(filename)})


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "managed"
        self.config = RecordingConfig(enabled=True, data_root=self.root,
                                      storage_quota_bytes=10**9, min_free_bytes=1024)
        initialize_storage(self.config)
        self.store = HistoryStore(self.config)
        self.addCleanup(self.store.close)

    def segment(self, name, start, end=None):
        relpath = "recordings/" + name + ".mp4"
        path = self.root / relpath
        path.write_bytes(b"test-media")
        self.store.start_segment(name, relpath, ts(start), codec="test")
        if end is not None:
            self.store.finish_segment(name, ts(end), len(b"test-media"), verified=True)
        return path

    def test_eighth_day_exact_cutoff_and_active_segment(self):
        old = self.segment("old", "2026-10-12T23:55:00", "2026-10-13T00:00:00")
        kept = self.segment("kept", "2026-10-13T00:00:00", "2026-10-13T00:05:00")
        crossing = self.segment("crossing", "2026-10-12T23:59:00", "2026-10-13T00:01:00")
        active = self.segment("active", "2026-10-12T20:00:00")
        orphan = self.root / "recordings/unindexed.mp4"
        orphan.write_bytes(b"unmanaged by index")
        result = cleanup_expired(self.store, ts("2026-10-19T00:00:00"), True)
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(all(path.exists() for path in (kept, crossing, active, orphan)))

    def test_month_end_and_year_end_boundaries(self):
        for prefix, oldstart, oldend, now in (
            ("month", "2026-09-30T23:58:00", "2026-10-01T00:00:00", "2026-10-07T00:00:00"),
            ("year", "2026-12-31T23:58:00", "2027-01-01T00:00:00", "2027-01-07T00:00:00"),
        ):
            with self.subTest(prefix=prefix):
                path = self.segment(prefix, oldstart, oldend)
                self.assertEqual(cleanup_expired(self.store, ts(now), True)["deleted"], 1)
                self.assertFalse(path.exists())

    def test_time_trust_rollback_dry_run_and_restart_cleanup(self):
        path = self.segment("old", "2026-10-12T01:00:00", "2026-10-12T01:05:00")
        now = ts("2026-10-19T12:00:00")
        self.assertEqual(cleanup_expired(self.store, now)["skipped"], "untrusted_time")
        self.assertEqual(cleanup_expired(self.store, now, True, dry_run=True)["candidates"], 1)
        self.assertTrue(path.exists())
        cleanup_expired(self.store, now, True)
        other = HistoryStore(self.config)
        self.addCleanup(other.close)
        self.assertEqual(cleanup_expired(other, now - 1, True)["skipped"], "clock_rollback")
        self.assertEqual(cleanup_expired(other, now, True)["deleted"], 0)

    def test_unlink_failure_stays_pending_then_retries_after_restart(self):
        path = self.segment("retry", "2026-10-12T01:00:00", "2026-10-12T01:05:00")
        now = ts("2026-10-19T12:00:00")
        with patch.object(Path, "unlink", side_effect=PermissionError("busy")):
            result = cleanup_expired(self.store, now, True)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(self.store.get_recording("retry")["state"], "pending_delete")
        self.assertTrue(path.exists())
        other = HistoryStore(self.config)
        self.addCleanup(other.close)
        self.assertEqual(cleanup_expired(other, now + 1, True)["deleted"], 1)
        self.assertIsNone(other.get_recording("retry"))

    def test_missing_file_delete_is_idempotent(self):
        path = self.segment("missing", "2026-10-12T01:00:00", "2026-10-12T01:05:00")
        path.unlink()
        result = cleanup_expired(self.store, ts("2026-10-19T12:00:00"), True)
        self.assertEqual(result["deleted"], 1)

    def test_pending_protection_expires_and_cleanup_never_deletes_database(self):
        path = self.segment("leased", "2026-10-12T01:00:00", "2026-10-12T01:05:00")
        now = ts("2026-10-19T12:00:00")
        self.store._execute("UPDATE recordings SET lease_until=? WHERE id=?", (now + 60, "leased"))
        self.assertEqual(cleanup_expired(self.store, now, True)["deleted"], 0)
        self.assertTrue(path.exists())
        self.assertEqual(cleanup_expired(self.store, now + 61, True)["deleted"], 1)
        self.store._execute("INSERT INTO recordings(id,relpath,started_at,ended_at,state) VALUES(?,?,?,?,?)",
                            ("bad-db-pointer", "db/history.db", 1, 2, "complete"))
        result = cleanup_expired(self.store, now + 62, True)
        self.assertEqual(result["deleted"], 0)
        self.assertTrue((self.root / "db/history.db").exists())
        self.assertEqual(len(result["errors"]), 1)

    def test_corrupt_sqlite_intervals_and_leases_are_retained(self):
        """Inject real rows bypassing public validation, as a damaged index can."""
        now = ts("2026-10-19T12:00:00")
        old = ts("2026-10-12T12:00:00")
        cases = (
            ("inverted-new", now, 1.0, 0),
            ("inverted-old", old, 1.0, 0),
            ("start-inf", float("inf"), old, 0),
            ("start-negative-inf", -float("inf"), old, 0),
            ("start-text", "not-a-time", old, 0),
            ("end-inf", old, float("inf"), 0),
            ("end-negative-inf", old, -float("inf"), 0),
            ("end-nan", old, float("nan"), 0),
            ("end-text", old, "bad-time", 0),
            ("lease-inf", old, old + 10, float("inf")),
            ("lease-negative-inf", old, old + 10, -float("inf")),
            ("lease-negative", old, old + 10, -1),
            ("lease-text", old, old + 10, "not-a-lease"),
        )
        for name, started, ended, lease in cases:
            relpath = "recordings/" + name + ".mp4"
            (self.root / relpath).write_bytes(b"keep-invalid-index")
            self.store._execute(
                "INSERT INTO recordings(id,relpath,started_at,ended_at,state,lease_until) VALUES(?,?,?,?,'complete',?)",
                (name, relpath, started, ended, lease))
        good = self.segment("valid-old", "2026-10-12T10:00:00", "2026-10-12T10:05:00")
        dry = cleanup_expired(self.store, now, True, dry_run=True)
        self.assertEqual(dry["candidates"], 1)
        self.assertEqual(len(dry["errors"]), len(cases))
        self.assertTrue(good.exists())
        result = cleanup_expired(self.store, now, True)
        self.assertEqual(result["deleted"], 1)
        self.assertFalse(good.exists())
        self.assertEqual(len(result["errors"]), len(cases))
        for name, _, _, _ in cases:
            with self.subTest(name=name):
                self.assertTrue((self.root / "recordings" / (name + ".mp4")).exists())
                self.assertIsNotNone(self.store.get_recording(name))
        # SQLite converts bound NaN to SQL NULL, hence nullable ended_at above.
        self.assertIsNone(self.store.get_recording("end-nan")["ended_at"])

    def test_corrupt_event_and_gap_intervals_are_not_deleted(self):
        now = ts("2026-10-19T12:00:00")
        self.store._execute(
            "INSERT INTO events(id,kind,started_at,ended_at,payload) VALUES(?, ?, ?, ?, ?)",
            ("corrupt-event", "fall", now, 1.0, "{}"))
        self.store._execute("INSERT INTO gaps(id,started_at,ended_at,reason) VALUES(?,?,?,?)",
                            ("corrupt-gap", float("inf"), 1.0, "bad-index"))
        result = cleanup_expired(self.store, now, True)
        self.assertEqual(result["events_deleted"], 0)
        self.assertEqual(result["gaps_deleted"], 0)
        self.assertIsNotNone(self.store.get_event("corrupt-event"))
        self.assertEqual(len(self.store.list_gaps()), 1)
        self.assertEqual(len(result["errors"]), 2)

    def test_device_boundary_checks_with_mock_stat_not_real_mount_validation(self):
        """Windows unit test simulates st_dev; board mount topology is untested."""
        nested = self.root / "recordings/day"
        nested.mkdir()
        media = nested / "sample.mp4"
        media.write_bytes(b"keep")
        original_stat = Path.stat
        def device_spoof(target):
            def altered(path, *args, **kwargs):
                info = original_stat(path, *args, **kwargs)
                if path == target:
                    values = list(info)
                    values[2] = info.st_dev + 1
                    return os.stat_result(values)
                return info
            return altered
        # Immediate managed subtree, deeper parent, final file, and marker.
        for target in (self.root / "recordings", nested, media, self.root / MARKER_NAME):
            with self.subTest(target=str(target)), patch.object(Path, "stat", device_spoof(target)):
                with self.assertRaises(ValueError):
                    safe_managed_path(self.config, "recordings/day/sample.mp4", must_exist=True)
                with self.assertRaises(ValueError):
                    managed_usage(self.config)
                if target in (self.root / "recordings", self.root / MARKER_NAME):
                    with self.assertRaises(ValueError):
                        validate_storage(self.config)
        self.assertTrue(media.exists())

    def test_cleanup_rejects_indexed_file_on_mock_other_device(self):
        path = self.segment("other-device", "2026-10-12T01:00:00", "2026-10-12T01:05:00")
        original_stat = Path.stat
        def altered(candidate, *args, **kwargs):
            info = original_stat(candidate, *args, **kwargs)
            if candidate == path:
                values = list(info)
                values[2] = info.st_dev + 1
                return os.stat_result(values)
            return info
        with patch.object(Path, "stat", altered):
            result = cleanup_expired(self.store, ts("2026-10-19T12:00:00"), True)
        self.assertTrue(path.exists())
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(len(result["errors"]), 1)

    def test_removed_database_is_not_silently_recreated(self):
        database = self.root / "db/history.db"
        database.unlink()
        with self.assertRaises(FileNotFoundError):
            self.store.list_recordings()
        self.assertFalse(database.exists())

    def test_recording_completes_only_after_final_file_size_matches(self):
        self.store.start_segment("pending", "tmp/pending.mp4", ts("2026-10-19T00:00:00"))
        final = self.root / "recordings/final.mp4"
        with self.assertRaises(FileNotFoundError):
            self.store.finish_segment("pending", ts("2026-10-19T00:01:00"), 10,
                                      relpath="recordings/final.mp4")
        final.write_bytes(b"final")
        with self.assertRaises(ValueError):
            self.store.finish_segment("pending", ts("2026-10-19T00:01:00"), 10,
                                      relpath="recordings/final.mp4")
        self.assertEqual(self.store.get_recording("pending")["state"], "recording")
        self.store.finish_segment("pending", ts("2026-10-19T00:01:00"), 5,
                                  relpath="recordings/final.mp4")
        self.assertEqual(self.store.get_recording("pending")["state"], "complete")

    def test_two_instances_coordinate_threaded_short_connection_writes(self):
        second = HistoryStore(self.config)
        self.addCleanup(second.close)
        def insert(index):
            store = self.store if index % 2 else second
            return store.add_event("fall", ts("2026-10-19T00:00:00"), person_id=index)
        with ThreadPoolExecutor(max_workers=4) as pool:
            identifiers = list(pool.map(insert, range(20)))
        self.assertEqual(len(set(identifiers)), 20)
        self.assertEqual(len(self.store.list_events(limit=50)), 20)

    def test_events_crossing_cutoff_and_open_events_are_kept(self):
        start = ts("2026-10-12T23:59:00")
        old = self.store.add_event("fall", start, ended_at=ts("2026-10-13T00:00:00"))
        crossing = self.store.add_event("fall", start, ended_at=ts("2026-10-13T00:01:00"))
        opened = self.store.add_event("fall", start)
        cleanup_expired(self.store, ts("2026-10-19T12:00:00"), True)
        self.assertIsNone(self.store.get_event(old))
        self.assertIsNotNone(self.store.get_event(crossing))
        self.assertIsNotNone(self.store.get_event(opened))

    def test_invalid_media_paths_and_index_injection_cannot_delete_outside(self):
        outside = Path(self.temp.name) / "do-not-delete.mp4"
        outside.write_bytes(b"outside")
        for name in ("../do-not-delete.mp4", "recordings/../../do-not-delete.mp4",
                     "/tmp/file", "C:/file", "recordings\\file", "recordings//file"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_managed_path(self.config, name)
        # Simulate a corrupt row bypassing the validated public insertion API.
        self.store._execute("INSERT INTO recordings(id,relpath,started_at,ended_at,state) VALUES(?,?,?,?,?)",
                            ("corrupt", "../do-not-delete.mp4", 1, 2, "complete"))
        result = cleanup_expired(self.store, ts("2026-10-19T12:00:00"), True)
        self.assertEqual(result["deleted"], 0)
        self.assertEqual(len(result["errors"]), 1)
        self.assertTrue(outside.exists())

    def test_symlink_and_hardlink_rejected_when_available(self):
        target = Path(self.temp.name) / "outside.mp4"
        target.write_bytes(b"keep")
        link = self.root / "recordings/link.mp4"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            # Windows without Developer Mode often disallows symlink creation.
            pass
        else:
            with self.assertRaises(ValueError):
                safe_managed_path(self.config, "recordings/link.mp4")
            link.unlink()
        hard = self.root / "recordings/hard.mp4"
        try:
            os.link(str(target), str(hard))
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(ValueError):
            safe_managed_path(self.config, "recordings/hard.mp4")

    def test_marker_missing_never_recreated_by_cleanup_or_validation(self):
        marker = self.root / MARKER_NAME
        marker.unlink()
        for operation in (lambda: validate_storage(self.config),
                          lambda: cleanup_expired(self.store, ts("2026-10-19T12:00:00"), True)):
            with self.assertRaises(ValueError):
                operation()
        self.assertFalse(marker.exists())

    def test_refuses_to_claim_nonempty_unknown_root_or_new_owner(self):
        outside = Path(self.temp.name) / "unknown"
        outside.mkdir()
        (outside / "valuable.txt").write_text("keep")
        config = RecordingConfig(enabled=True, data_root=outside,
                                 storage_quota_bytes=10**9, min_free_bytes=1024)
        with self.assertRaises(ValueError):
            initialize_storage(config)
        marker_path = self.root / MARKER_NAME
        marker = json.loads(marker_path.read_text())
        marker["id"] = "f" * 32
        marker_path.write_text(json.dumps(marker))
        with self.assertRaises(ValueError):
            self.store.list_recordings()

    def test_metadata_parameter_binding_and_actual_usage(self):
        event = self.store.add_event("fall' OR 1=1 --", ts("2026-10-19T00:00:00"), payload={"text": "异常"})
        self.assertEqual(self.store.get_event(event)["payload"], {"text": "异常"})
        self.assertEqual(len(self.store.list_events(kind="fall' OR 1=1 --")), 1)
        baseline = self.store.managed_size_bytes()
        (self.root / "tmp/partial").write_bytes(b"a" * 8192)
        self.assertGreaterEqual(self.store.managed_size_bytes(), baseline + 8192)
        self.assertEqual(storage_status(self.config)["used_bytes"], self.store.managed_size_bytes())
        db = sqlite3.connect(str(self.root / "db/history.db"))
        try:
            self.assertEqual(db.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        finally:
            db.close()
        with self.assertRaises(ValueError):
            self.store.list_events(limit=201)

    def test_external_history_ids_are_validated_before_insert(self):
        for identifier in ("external.id", "", None, 1, True, [], {}, "a b", "a/b", "a\\b", "中文", "x" * 129, "id\n"):
            with self.subTest(identifier=identifier), patch.object(self.store, "_execute") as execute:
                with self.assertRaises(ValueError):
                    self.store.start_segment(identifier, "recordings/invalid.mp4", 1.0)
                with self.assertRaises(ValueError):
                    self.store.add_event("fall", 1.0, event_id=identifier)
                execute.assert_not_called()
        for index, identifier in enumerate(("A_b-9", "x" * 128)):
            self.store.start_segment(identifier, "recordings/valid-" + str(index) + ".mp4", 1.0)
            self.store.add_event("fall", 1.0, event_id=identifier)
            self.assertEqual(self.store.get_recording(identifier)["id"], identifier)
            self.assertEqual(self.store.get_event(identifier)["id"], identifier)
        generated = self.store.add_event("fall", 1.0)
        self.assertEqual(len(generated), 32)
        self.assertEqual(self.store.get_event(generated)["id"], generated)

    def test_event_kind_contract_is_shared_by_insert_and_filter(self):
        for kind in ("fall detected", "检测到跌倒", " ", "x" * 100):
            event_id = self.store.add_event(kind, 1.0)
            self.assertEqual([row["id"] for row in self.store.list_events(kind=kind)], [event_id])
            self.assertEqual([row["id"] for row in self.store.list_events(event_type=kind)], [event_id])
        for kind in ("", "x" * 101, None, 1, []):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.store.add_event(kind, 1.0)
        for kind in ("", "x" * 101, 1, []):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.store.list_events(kind=kind)


if __name__ == "__main__":
    unittest.main()
