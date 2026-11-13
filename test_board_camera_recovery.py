"""Exercise deployed camera methods without importing hardware or credentials.

BOARD_CAMERA_SOURCE points to the two full board sources; they stay outside Git.
"""
import ast
import asyncio
import os
from pathlib import Path
import threading
import time
import types
import unittest
from unittest.mock import Mock


SOURCE = Path(os.environ.get('BOARD_CAMERA_SOURCE', '.tmp/migration-repair-20260908/board-edited'))


def extract(filename, class_name=None, names=(), namespace=None):
    tree = ast.parse((SOURCE / filename).read_text(encoding='utf-8'))
    body = tree.body
    if class_name:
        body = next(n for n in body if isinstance(n, ast.ClassDef) and n.name == class_name).body
    nodes = [n for n in body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in names]
    for node in nodes:
        node.decorator_list = []
    env = dict(namespace or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, 'exec'), env)
    return env


class StopEvent:
    def __init__(self, after_wait=None):
        self.stopped = False
        self.waits = []
        self.after_wait = after_wait

    def is_set(self):
        return self.stopped

    def set(self):
        self.stopped = True

    def clear(self):
        self.stopped = False

    def wait(self, seconds):
        self.waits.append(seconds)
        if self.after_wait:
            self.after_wait()
        return self.stopped


@unittest.skipUnless((SOURCE / 'ascend_main_other.py').is_file(), 'Set BOARD_CAMERA_SOURCE to the private board source directory')
class CameraRecoveryTests(unittest.TestCase):
    def detector(self):
        names = ('init', '_camera_reader_thread', '_clear_camera_frames', 'camera_is_live', 'stop')
        self.resource = Mock()
        self.thread = Mock()
        env = extract('ascend_main_other.py', 'AclLiteStreamDetector', names, {
            'time': time,
            'threading': types.SimpleNamespace(Thread=Mock(return_value=self.thread)),
            'AclLiteResource': Mock(return_value=self.resource),
            'AclLiteModel': Mock(), 'AclLiteImageProc': Mock(),
        })
        cls = type('Detector', (), {n: env[n] for n in names if n in env})
        d = cls()
        d.running = False
        d.cap = None
        d.camera_connected = False
        d.camera_connected_since = 0.0
        d.last_camera_frame_at = 0.0
        d.camera_stop = StopEvent()
        d.camera_thread = None
        d.frame_lock = threading.Lock()
        d.result_lock = threading.Lock()
        d.frame_ready = threading.Event()
        d.result_ready = threading.Event()
        d.latest_frame = None
        d.latest_result = None
        d._last_capture_ts = 0
        d._capture_interval = 0
        d.inference_enabled = True
        d.face_recognizer = Mock()
        d.face_detector = Mock()
        d.face_library = Mock()
        d.model_path = 'model.om'
        d._log_model_info = Mock()
        d._camera_candidates = Mock(return_value=[0])
        d._open_camera_with_fallback = Mock(return_value=False)
        return d

    def test_start_without_camera_keeps_npu_and_reader_alive(self):
        d = self.detector()
        self.assertTrue(d.init())
        self.resource.init.assert_called_once()
        self.thread.start.assert_called_once()
        self.assertTrue(d.running)

    def test_late_attach_is_retried_without_npu_reinit(self):
        d = self.detector()
        d.running = True
        cap = Mock()
        frame = Mock()
        calls = []

        def open_camera():
            calls.append(1)
            if len(calls) == 1:
                return False
            d.cap = cap
            return True

        reads = []

        def read():
            if reads:
                self.assertTrue(d.camera_is_live())
                self.assertIsNotNone(d.latest_frame)
                d.running = False
            reads.append(1)
            return True, frame

        d._open_camera_with_fallback = Mock(side_effect=open_camera)
        cap.read.side_effect = read
        d._camera_reader_thread()
        self.assertEqual(2, len(calls))
        self.assertEqual([3.0], d.camera_stop.waits)
        self.assertEqual(2, len(reads))
        self.resource.init.assert_not_called()
        cap.release.assert_called_once()

    def test_disconnect_clears_frames_then_reconnects(self):
        d = self.detector()
        d.running = True
        old = Mock()
        old.read.side_effect = [(False, None), RuntimeError('reader did not reconnect')]
        d.cap = old
        d.camera_connected = True
        d.latest_frame = 'stale'
        d.latest_result = 'stale'
        new = Mock()

        def waited():
            self.assertIsNone(d.latest_frame)
            self.assertIsNone(d.latest_result)
            self.assertFalse(d.camera_connected)

        def reopen():
            d.cap = new
            return True

        def read():
            d.running = False
            return True, Mock()

        d.camera_stop.after_wait = waited
        d._open_camera_with_fallback.side_effect = reopen
        new.read.side_effect = read
        d._camera_reader_thread()
        old.release.assert_called_once()
        d._open_camera_with_fallback.assert_called_once()
        self.assertIsNone(d.cap)

    def test_shutdown_interrupts_retry(self):
        d = self.detector()
        d.running = True
        d.camera_stop.after_wait = d.stop
        d._camera_reader_thread()
        self.assertTrue(d.camera_stop.is_set())
        d._open_camera_with_fallback.assert_called_once()

    def test_stop_clears_existing_frames(self):
        d = self.detector()
        d.running = True
        d.latest_frame = 'stale'
        d.latest_result = 'stale'
        d.stop()
        self.assertIsNone(d.latest_frame)
        self.assertIsNone(d.latest_result)

    def test_stop_also_signals_reader_before_camera_open_completes(self):
        d = self.detector()
        d.camera_thread = Mock()
        d.stop()
        self.assertTrue(d.camera_stop.is_set())
        d.camera_thread.join.assert_called_once_with(timeout=4.0)

    def server(self):
        d = self.detector()
        d.running = True
        d.camera_connected = True
        d.camera_connected_since = time.monotonic() - 1
        d.last_camera_frame_at = time.monotonic()
        hw = Mock()
        hw.get_current_frame.return_value = b'jpeg'
        hw.get_stats.return_value = dict(fps=8, detections=1, fall_count=0, status='正常',
                                        mqtt_connected=True, start_time=time.time(), frame_count=5)
        env = extract('ascend_board_server.py', names=('camera_video_is_live', 'api_stats', 'video_frame'), namespace={
            'system_detector': d, 'video_frame_started_at': time.monotonic(), 'time': time,
            'video_hw': hw, 'JSONResponse': lambda data: data,
            'Response': lambda **kwargs: kwargs,
        })
        return d, hw, env

    def test_stale_camera_has_zero_fps_and_no_jpeg(self):
        d, hw, env = self.server()
        d.last_camera_frame_at = time.monotonic() - 4
        stats = asyncio.run(env['api_stats']())
        self.assertEqual(0, stats['fps'])
        self.assertFalse(stats['camera_connected'])
        self.assertEqual('摄像头离线', stats['status'])
        self.assertEqual(204, asyncio.run(env['video_frame']())['status_code'])

    def test_reconnect_does_not_republish_previous_camera_frame(self):
        d, hw, env = self.server()
        d.camera_connected_since = time.monotonic() + 0.001
        self.assertEqual(204, asyncio.run(env['video_frame']())['status_code'])

    def test_stalled_inference_does_not_republish_old_jpeg(self):
        d, hw, env = self.server()
        env['video_frame_started_at'] = time.monotonic() - 4
        self.assertEqual(204, asyncio.run(env['video_frame']())['status_code'])
        self.assertEqual(0, asyncio.run(env['api_stats']())['fps'])

    def test_live_frame_and_stats_preserved(self):
        d, hw, env = self.server()
        self.assertEqual(b'jpeg', asyncio.run(env['video_frame']())['content'])
        stats = asyncio.run(env['api_stats']())
        self.assertEqual(8, stats['fps'])
        self.assertTrue(stats['camera_connected'])


if __name__ == '__main__':
    unittest.main()
