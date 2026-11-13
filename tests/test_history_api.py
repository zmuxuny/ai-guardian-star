"""Real ASGI requests and temporary SQLite; no board, camera or network service."""

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
if not all(importlib.util.find_spec(name) for name in ("fastapi", "httpx")):
    raise unittest.SkipTest("history API tests require real FastAPI and httpx dependencies")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from guardian_history import HistoryStore
from guardian_history_api import create_history_router, file_response_capability
from guardian_recording_config import RecordingConfig
from guardian_storage import initialize_storage


TOKEN = "test-history-credential"
AUTH = {"Authorization": "Bearer " + TOKEN}
START = datetime(2026, 10, 18, tzinfo=timezone.utc).timestamp()
WINDOW = {"start": "2026-10-18T00:00:00Z", "end": "2026-10-19T00:00:00Z"}


def client_for(config, store=None):
    app = FastAPI()
    app.include_router(create_history_router(config, store))
    return TestClient(app)


class HistoryApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "managed"
        self.config = RecordingConfig(
            enabled=True, data_root=self.root,
            storage_quota_bytes=64 * 1024 * 1024, min_free_bytes=1,
            history_token=TOKEN,
        )
        initialize_storage(self.config)
        self.store = HistoryStore(self.config)
        self.store.start_segment("segment-1", "recordings/2026-10-18/part.mp4", START)
        self.event_id = self.store.add_event(
            "fall", START + 10, person_id="track-1", ended_at=START + 20,
            payload={"score": 0.9, "message": "检测到跌倒", "path": "recordings/private.mp4"},
            extra={"internal": "C:\\device\\secret.db", "safe": 2},
        )
        self.client = client_for(self.config, self.store)

    def tearDown(self):
        self.client.close()
        self.store.close()
        self.temporary.cleanup()

    def test_router_and_disabled_store_do_not_create_files(self):
        path = Path(self.temporary.name) / "untouched"
        config = RecordingConfig(data_root=path, history_token=TOKEN)
        with client_for(config) as client:
            status = client.get("/api/history/status", headers=AUTH)
            self.assertEqual(status.status_code, 200)
            self.assertEqual(status.json()["state"], "disabled")
            self.assertEqual(client.get("/api/history/recordings", headers=AUTH).status_code, 503)
        self.assertFalse(path.exists())

    def test_all_routes_fail_closed_without_or_with_wrong_credentials(self):
        paths = (
            "/status", "/recordings", "/events", "/events/unknown",
            "/recordings/segment-1/video", "/events/unknown/snapshot",
        )
        for path in paths:
            for headers in ({}, {"Authorization": "Bearer incorrect"}, {"Authorization": "Basic " + TOKEN}):
                with self.subTest(path=path, headers=bool(headers)):
                    response = self.client.get("/api/history" + path, headers=headers)
                    self.assertEqual(response.status_code, 401)
                    self.assertNotIn(TOKEN, response.text)
        with client_for(RecordingConfig()) as client:
            self.assertEqual(client.get("/api/history/status").status_code, 503)

    def test_query_token_is_not_authentication(self):
        response = self.client.get("/api/history/events", params={"token": TOKEN})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn(TOKEN, response.text)

    def test_status_is_preparation_not_a_recording_claim(self):
        status = self.client.get("/api/history/status", headers=AUTH).json()
        self.assertEqual(status["state"], "encoder_not_configured")
        self.assertFalse(status["recording_backend_ready"])
        self.assertFalse(status["capture_integrated"])
        self.assertTrue(status["media_download_enabled"])  # 下载已实现：按版本放行
        self.assertFalse(status["resume_verified"])
        self.assertNotIn(str(self.root), str(status))
        with client_for(SimpleNamespace(enabled=True, history_token=TOKEN, encoder="candidate")) as client:
            self.assertEqual(client.get("/api/history/status", headers=AUTH).json()["state"], "prepared")

    def test_real_sqlite_queries_and_pagination(self):
        self.store.add_event("sit", START + 30, ended_at=START + 31)
        events = self.client.get("/api/history/events", params={**WINDOW, "kind": "fall"}, headers=AUTH)
        self.assertEqual(events.status_code, 200)
        self.assertEqual([row["id"] for row in events.json()["items"]], [self.event_id])
        self.assertEqual(events.json()["items"][0]["started_at"], "2026-10-18T00:00:10Z")
        page = self.client.get("/api/history/events", params={**WINDOW, "limit": 1, "offset": 1}, headers=AUTH)
        self.assertEqual([row["id"] for row in page.json()["items"]], [self.event_id])
        recordings = self.client.get("/api/history/recordings", params=WINDOW, headers=AUTH)
        self.assertEqual(recordings.status_code, 200)
        self.assertEqual(recordings.json()["items"][0]["id"], "segment-1")
        self.assertNotIn("relpath", recordings.text)
        self.assertNotIn("part.mp4", recordings.text)

    def test_event_list_embeds_linked_recordings_in_one_batch(self):
        other = self.store.add_event("sit", START + 30, ended_at=START + 31)
        self.store.link_event_recording(self.event_id, "segment-1", START + 11)
        response = self.client.get("/api/history/events", params=WINDOW, headers=AUTH)
        self.assertEqual(response.status_code, 200)
        items = {row["id"]: row for row in response.json()["items"]}
        self.assertEqual([clip["id"] for clip in items[self.event_id]["recordings"]], ["segment-1"])
        self.assertEqual(items[other]["recordings"], [])
        self.assertNotIn("part.mp4", response.text)
        with patch.object(self.store, "list_event_recordings",
                          side_effect=AssertionError("list must not query per event")):
            self.assertEqual(self.client.get("/api/history/events", params=WINDOW,
                                             headers=AUTH).status_code, 200)

    def test_detail_filters_private_metadata_and_paths(self):
        self.store.add_event("fall", START, event_id="private-event", payload={
            "credential": TOKEN, "a": "relative/file.mp4", "b": "/etc/private",
            "c": "hidden.mp4", "nested": {"/private": 1, "safe": True},
        })
        response = self.client.get("/api/history/events/private-event", headers=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["payload"], {"nested": {"safe": True}})
        response = self.client.get("/api/history/events/" + self.event_id, headers=AUTH)
        self.assertIn("检测到跌倒", response.text)
        self.assertNotIn("secret.db", response.text)
        self.assertNotIn("private.mp4", response.text)

    def test_detail_not_found_and_injection_id(self):
        self.assertEqual(self.client.get("/api/history/events/unknown", headers=AUTH).status_code, 404)
        self.assertEqual(self.client.get("/api/history/events/a%27OR1=1", headers=AUTH).status_code, 422)
        self.assertEqual(len(self.store.list_events()), 1)

    def test_unicode_space_and_bound_sql_kinds_match_store_and_detail(self):
        for index, kind in enumerate(("fall detected", "检测到跌倒", " ", "fall' OR 1=1 --", "x" * 100)):
            with self.subTest(kind=kind):
                event_id = self.store.add_event(kind, START + 40, event_id="external_event-" + str(index))
                response = self.client.get("/api/history/events", params={**WINDOW, "kind": kind}, headers=AUTH)
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["id"] for row in response.json()["items"]], [event_id])
                self.assertEqual(response.json()["items"][0]["kind"], kind)
                detail = self.client.get("/api/history/events/" + event_id, headers=AUTH)
                self.assertEqual(detail.status_code, 200)
                self.assertEqual(detail.json()["kind"], kind)
                self.assertEqual([row["id"] for row in self.store.list_events(kind=kind)], [event_id])
        self.assertEqual(len(self.store.list_events()), 6)

    def test_invalid_external_ids_never_enter_store_and_valid_ids_are_addressable(self):
        for value in ("external.id", "", None, 17, [], {}, "a b", "a/b", "a\\b", "中文", "x" * 129, "id\n"):
            with self.subTest(identifier=value):
                with self.assertRaises(ValueError):
                    self.store.add_event("fall", START + 50, event_id=value)
                with self.assertRaises(ValueError):
                    self.store.start_segment(value, "recordings/invalid.mp4", START)
        self.assertEqual(len(self.store.list_events()), 1)
        self.assertEqual(len(self.store.list_recordings()), 1)
        for index, valid in enumerate(("A_b-9", "a" * 128)):
            self.store.add_event("fall detected", START, event_id=valid)
            self.store.start_segment(valid, "recordings/valid-" + str(index) + ".mp4", START)
            detail = self.client.get("/api/history/events/" + valid, headers=AUTH)
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(detail.json()["id"], valid)

    def test_invalid_queries_do_not_echo_inputs_or_reach_store(self):
        cases = (
            {"limit": "0"}, {"limit": "201"}, {"offset": "-1"}, {"offset": "100001"},
            {"start": "2026-10-18"}, {"start": "bad"},
            {"start": "2026-10-19T00:00:00Z", "end": "2026-10-18T00:00:00Z"},
            {"start": "2026-01-01T00:00:00Z", "end": "2026-10-19T00:00:00Z"},
            {"kind": ""}, {"kind": "x" * 101}, {"path": "/etc/private"}, {"limit": TOKEN},
        )
        with patch.object(self.store, "list_events") as call:
            for params in cases:
                response = self.client.get("/api/history/events", params=params, headers=AUTH)
                self.assertEqual(response.status_code, 422, params)
                self.assertNotIn(TOKEN, response.text)
                self.assertNotIn("/etc/private", response.text)
            call.assert_not_called()
        duplicate = self.client.get("/api/history/events?limit=1&limit=2", headers=AUTH)
        self.assertEqual(duplicate.status_code, 422)

    def test_query_date_window_is_bounded_and_timezone_normalized(self):
        with patch.object(self.store, "list_events", return_value=[]) as call:
            response = self.client.get("/api/history/events", params={"start": "2026-10-18T08:00:00+08:00"}, headers=AUTH)
            self.assertEqual(response.status_code, 200)
            args = call.call_args.kwargs
            self.assertEqual(args["start"], START)
            self.assertEqual(args["end"] - args["start"], 31 * 86400)
            self.client.get("/api/history/events", headers=AUTH)
            args = call.call_args.kwargs
            self.assertEqual(args["end"] - args["start"], 31 * 86400)

    def test_store_errors_hide_sql_and_device_paths(self):
        with patch.object(self.store, "list_events", side_effect=RuntimeError("SELECT * FROM secret /root/private.db " + TOKEN)):
            response = self.client.get("/api/history/events", headers=AUTH)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "history_query_unavailable"})

    def test_media_routes_fail_closed_for_incomplete_or_unknown(self):
        response = self.client.get("/api/history/recordings/segment-1/video",
                                   headers={**AUTH, "Range": "bytes=0-1"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "media_not_ready")
        snapshot = self.client.get("/api/history/events/unknown/snapshot", headers=AUTH)
        self.assertEqual(snapshot.status_code, 503)
        self.assertEqual(snapshot.json()["detail"], "media_not_implemented")
        self.assertNotIn("accept-ranges", snapshot.headers)

    def test_completed_recording_downloads_and_leases(self):
        relpath = "recordings/2026-10-18/done.mp4"
        self.store.start_segment("done-1", relpath, START)
        media = self.config.data_root / relpath
        media.parent.mkdir(parents=True, exist_ok=True)
        media.write_bytes(b"FAKE VIDEO BYTES")
        self.store.finish_segment("done-1", START + 5, media.stat().st_size,
                                  relpath=relpath, duration_seconds=5.0)
        response = self.client.get("/api/history/recordings/done-1/video", headers=AUTH)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"FAKE VIDEO BYTES")
        disposition = response.headers.get("content-disposition", "")
        self.assertNotIn(str(self.config.data_root), disposition)
        row = self.store.get_recording("done-1")
        self.assertGreater(float(row["lease_until"]), time.time() + 60)
        ranged = self.client.get("/api/history/recordings/done-1/video",
                                 headers={**AUTH, "Range": "bytes=0-3"})
        self.assertEqual(ranged.status_code, 206)
        self.assertEqual(ranged.content, b"FAKE")
        self.assertEqual(self.client.get("/api/history/recordings/unknown9", headers=AUTH).status_code, 404)

    def test_missing_store_is_unavailable(self):
        with client_for(self.config) as client:
            self.assertEqual(client.get("/api/history/events", headers=AUTH).status_code, 503)

    def test_range_detection_never_claims_verified_resume(self):
        for installed, expected, download in (
                ("0.38.6", "unsupported_version", False),
                ("0.46.2", "version_capable_unverified", True),
                ("1.0.0rc1", "unknown", False)):
            with patch("guardian_history_api.metadata.version", return_value=installed):
                capability = file_response_capability()
                self.assertEqual(capability["file_response_range"], expected)
                self.assertFalse(capability["resume_verified"])
                self.assertEqual(capability["media_download_enabled"], download)


if __name__ == "__main__":
    unittest.main()
