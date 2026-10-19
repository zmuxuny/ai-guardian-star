"""Offline regressions; hardware imports are deliberately excluded from AST slices."""

import ast
import asyncio
from collections import deque
from pathlib import Path
import sys
import threading
import time
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from guardian_runtime import AlertEpisodeTracker, StationaryTimer, create_mqtt_client


def load_definition(file_name, name, namespace, method=None):
    """Load real function bodies without initializing ACL, cameras, audio or sockets."""
    tree = ast.parse((ROOT / "src" / file_name).read_text(encoding="utf-8"))
    node = next(node for node in tree.body if getattr(node, "name", None) == name)
    if method is not None:
        node = next(node for node in node.body if getattr(node, "name", None) == method)
    node.decorator_list = []
    module = ast.Module(body=[node], type_ignores=[])
    exec(compile(ast.fix_missing_locations(module), file_name, "exec"), namespace)
    return namespace[method or name]


class StationaryTests(unittest.TestCase):
    def test_duration_survives_short_history_at_multiple_frame_rates(self):
        is_sitting = load_definition(
            "ascend_main_other.py", "AclLiteStreamDetector",
            {"VLM_LONG_SIT_THRESHOLD_SECONDS": 10.0}, "_is_long_sit_state")
        for fps in (2, 10, 18):
            with self.subTest(fps=fps):
                timer = StationaryTimer()
                history = deque(maxlen=12)
                state = {"stationary_timer": timer, "box_history": history}
                for index in range(12 * fps + 1):
                    now = 100.0 + index / fps
                    timer.update([0, 0, 100, 200], now)
                    history.append((now, 100, 200, 2))
                    self.assertEqual(is_sitting(None, state, now), index >= 10 * fps)
                self.assertEqual(len(history), 12)
                self.assertEqual(timer.duration(112), 12)
                state["fall_confirmed"] = True
                self.assertFalse(is_sitting(None, state, 112))

    def test_horizontal_and_vertical_motion_restart_timer(self):
        for dx, dy in ((80, 0), (0, 80)):
            with self.subTest(dx=dx, dy=dy):
                timer = StationaryTimer()
                for index in range(101):
                    timer.update([0, 0, 100, 200], 100 + index / 10)
                self.assertEqual(timer.duration(110), 10)
                timer.update([dx, dy, 100 + dx, 200 + dy], 110.1)
                self.assertEqual(timer.duration(110.1), 0)

    def test_small_jitter_does_not_restart_timer(self):
        timer = StationaryTimer()
        for index in range(121):
            offset = index % 3 - 1
            timer.update([offset, offset, 100 + offset, 200 + offset], 100 + index / 10)
        self.assertEqual(timer.duration(112), 12)

    def test_gap_clock_reversal_and_horizontal_body_reset_timer(self):
        timer = StationaryTimer()
        timer.update([0, 0, 100, 200], 100)
        timer.update([0, 0, 100, 200], 101)
        self.assertEqual(timer.duration(106), 0)
        timer.update([0, 0, 100, 200], 106)
        self.assertEqual(timer.duration(106), 0)
        timer.update([0, 0, 100, 200], 99)
        self.assertEqual(timer.duration(99), 0)
        timer.update([0, 0, 200, 50], 100)
        self.assertIsNone(timer.since)


class EpisodeTests(unittest.TestCase):
    @staticmethod
    def alert(person_id=1, status="FALL DETECTED", stranger=True, sitting=False):
        return {"id": person_id, "status": status,
                "face_label": "stranger" if stranger else "known:member",
                "is_sitting": sitting}

    def test_sustained_event_counts_once_over_300_frames(self):
        tracker = AlertEpisodeTracker()
        totals = {"fall": 0, "sit": 0, "stranger": 0}
        for index in range(300):
            events = tracker.update([self.alert()], 100 + index / 10)
            for kind, values in events.items():
                totals[kind] += len(values)
        self.assertEqual(totals, {"fall": 1, "sit": 0, "stranger": 1})

    def test_recovery_then_new_event_and_multiple_people(self):
        tracker = AlertEpisodeTracker()
        self.assertEqual(len(tracker.update([self.alert(), self.alert(2)], 100)["fall"]), 2)
        tracker.update([self.alert(status="Normal", stranger=False), self.alert(2)], 101)
        events = tracker.update([self.alert(), self.alert(2)], 102)
        self.assertEqual([alert["id"] for alert in events["fall"]], [1])
        self.assertEqual([alert["id"] for alert in events["stranger"]], [1])

    def test_brief_missing_detection_does_not_duplicate_event(self):
        tracker = AlertEpisodeTracker()
        tracker.update([self.alert()], 100)
        tracker.update([], 100.1)
        self.assertFalse(tracker.update([self.alert()], 100.2)["fall"])
        self.assertEqual(len(tracker.update([self.alert()], 106)["fall"]), 1)

    def test_sitting_is_counted_per_person(self):
        tracker = AlertEpisodeTracker()
        first = self.alert(status="Normal", stranger=False, sitting=True)
        second = self.alert(2, status="Normal", stranger=False, sitting=True)
        self.assertEqual(len(tracker.update([first], 100)["sit"]), 1)
        self.assertEqual([a["id"] for a in tracker.update([first, second], 101)["sit"]], [2])

    def test_uncertain_identity_does_not_restart_stranger_event(self):
        tracker = AlertEpisodeTracker()
        tracker.update([self.alert()], 100)
        for index in range(1, 61):
            uncertain = self.alert()
            uncertain["face_label"] = "pending" if index % 2 else "unknown"
            tracker.update([uncertain], 100 + index / 10)
        self.assertFalse(tracker.update([self.alert()], 106.1)["stranger"])
        tracker.update([self.alert(status="Normal", stranger=False)], 106.2)
        self.assertEqual(len(tracker.update([self.alert()], 106.3)["stranger"]), 1)


class MqttTests(unittest.TestCase):
    def test_old_board_paho_does_not_receive_v2_keyword(self):
        mqtt = SimpleNamespace(Client=lambda client_id: client_id)
        self.assertEqual(create_mqtt_client(mqtt, "board"), "board")

    def test_paho_v2_explicitly_uses_callback_v2(self):
        version = object()
        mqtt = SimpleNamespace(Client=lambda **kwargs: kwargs,
                               CallbackAPIVersion=SimpleNamespace(VERSION2=version))
        self.assertEqual(create_mqtt_client(mqtt, "board"),
                         {"client_id": "board", "callback_api_version": version})


class AudioBroadcastTests(unittest.IsolatedAsyncioTestCase):
    async def run_broadcast(self, clients):
        sent = []
        audio = SimpleNamespace(get_audio_frame=lambda: b"pcm")
        namespace = {"audio_hw": audio, "ws_clients": clients,
                     "udp_socket": SimpleNamespace(sendto=lambda *args: sent.append(args)),
                     "phone_addr": ("127.0.0.1", 8888), "asyncio": asyncio,
                     "print": lambda *args: None}
        broadcast = load_definition("ascend_board_server.py", "mic_broadcast_task", namespace)
        task = asyncio.create_task(broadcast())
        try:
            # The real coroutine must yield even with no WebSocket clients.
            await asyncio.sleep(0)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        return sent

    async def test_udp_only_receives_microphone_frames(self):
        self.assertEqual(await self.run_broadcast([]), [(b"pcm", ("127.0.0.1", 8888))])

    async def test_broken_websocket_does_not_block_udp(self):
        async def broken_send(frame):
            raise ConnectionError("disconnected")
        clients = [SimpleNamespace(send_bytes=broken_send)]
        self.assertEqual(await self.run_broadcast(clients), [(b"pcm", ("127.0.0.1", 8888))])
        self.assertEqual(clients, [])


class InferenceTests(unittest.TestCase):
    def test_real_tracking_and_alert_flow_times_stillness_and_resets_after_fall(self):
        namespace = {"deque": deque, "StationaryTimer": StationaryTimer}
        tree = ast.parse((ROOT / "src/ascend_main_other.py").read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                try:
                    value = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        namespace[target.id] = value
        namespace["VLM_LONG_SIT_THRESHOLD_SECONDS"] = 10.0
        for name in ("compute_iou", "box_center", "box_diag",
                     "is_person_fallen", "analyze_fall_motion"):
            load_definition("ascend_main_other.py", name, namespace)
        detector = SimpleNamespace(person_states={}, person_state_lock=threading.Lock(),
                                   next_person_id=1, _prune_person_states=lambda now: None,
                                   _recover_active_known_track=lambda *args: None,
                                   _recover_recent_known_track=lambda *args: None)
        for name in ("_ensure_face_library_loaded", "_refresh_face_det_cache",
                     "_update_face_det_debug", "_maybe_recognize_face", "_maybe_trigger_vlm_events",
                     "_sync_face_library_revision"):
            setattr(detector, name, lambda *args, **kwargs: None)
        for name in ("_assign_person_ids", "_is_long_sit_state", "_build_alerts"):
            method = load_definition("ascend_main_other.py", "AclLiteStreamDetector", namespace, name)
            setattr(detector, name, MethodType(method, detector))
        frame = SimpleNamespace(shape=(480, 640, 3))
        detection = {"box": [100, 100, 200, 300], "kpts": [(0, 0, 0)] * 17}
        for index in range(121):
            alert = detector._build_alerts(frame, [detection], 100 + index / 10)[0]
            self.assertEqual(alert["is_sitting"], index >= 100)
        self.assertEqual(alert["sit_duration_sec"], 12)
        self.assertEqual(len(detector.person_states[1]["box_history"]), 12)
        # Visible shoulders below ankles trigger the real structural fall rule.
        keypoints = list(detection["kpts"])
        for index in (5, 6):
            keypoints[index] = (150, 250, 1)
        for index in (15, 16):
            keypoints[index] = (150, 200, 1)
        detection["kpts"] = keypoints
        for index in range(11):
            alert = detector._build_alerts(frame, [detection], 112.1 + index / 10)[0]
        self.assertEqual(alert["status"], "FALL DETECTED")
        self.assertFalse(alert["is_sitting"])
        self.assertIsNone(detector.person_states[1]["stationary_timer"].since)

    def test_throttled_frame_keeps_return_contract_and_is_not_an_observation(self):
        get_frame = load_definition("ascend_main_other.py", "AclLiteStreamDetector",
                                    {"time": time}, "get_detected_frame")
        frame = SimpleNamespace(copy=lambda: frame)
        detector = SimpleNamespace(running=True, inference_enabled=True,
                                   frame_lock=threading.Lock(), latest_frame=frame,
                                   frame_ready=threading.Event(), _last_infer_ts=100,
                                   _infer_interval=0.1, last_frame_inferred=True)
        with patch("time.time", return_value=100.01):
            self.assertEqual(get_frame(detector), (frame, []))
        self.assertFalse(detector.last_frame_inferred)


class StatsTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_or_disabled_inference_does_not_show_old_detection(self):
        stats = {"fps": 10, "detections": 1, "fall_count": 2, "status": "FALL",
                 "mqtt_connected": True, "start_time": time.time(),
                 "face_label": "stranger", "faces": [{"label": "stranger"}]}
        detector = SimpleNamespace(camera_is_live=lambda: True, inference_enabled=True,
                                   last_successful_inference_at=100)
        namespace = {"system_detector": detector, "time": time,
                     "camera_video_is_live": lambda: True, "JSONResponse": lambda value: value,
                     "video_hw": SimpleNamespace(get_stats=lambda: stats)}
        get_stats = load_definition("ascend_board_server.py", "api_stats", namespace)
        with patch("time.monotonic", return_value=101):
            self.assertEqual((await get_stats())["detections"], 1)
        with patch("time.monotonic", return_value=104):
            result = await get_stats()
            self.assertEqual(result["status"], "等待有效推理")
            self.assertEqual(result["detections"], 0)
            self.assertEqual(result["fps"], 0)
            self.assertEqual(result["faces"], [])
            self.assertEqual(result["fall_count"], 2)
        detector.inference_enabled = False
        with patch("time.monotonic", return_value=101):
            self.assertEqual((await get_stats())["status"], "推理已暂停")
        self.assertEqual(stats["detections"], 1)


if __name__ == "__main__":
    unittest.main()
