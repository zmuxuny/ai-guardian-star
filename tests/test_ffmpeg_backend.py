"""Offline checks for the ffmpeg backend: command shape and media verification.

No encoder runs here.  Real encoding is verified on the board (see
docs/修改记录/2026-10-22-异常触发录像实现接线.md).
"""

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from guardian_ffmpeg_backend import FfmpegBackendError, FfmpegSegmentBackend
from guardian_recording import FramePacket
from guardian_recording_config import RecordingConfig


class FakeProc:
    def __init__(self, returncode=0, errors=b""):
        self._final_returncode = returncode
        self.returncode = None
        self._errors = errors
        self.stdin = SimpleNamespace(closed=False, write=self._write, close=self._close)
        self.killed = False

    def _write(self, data):
        if self.killed:
            raise BrokenPipeError

    def _close(self):
        self.stdin.closed = True

    def communicate(self, timeout=None):
        self.returncode = self._final_returncode
        return None, self._errors

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -9


def probe_json(codec="h264", width=640, height=480, duration="3.0"):
    return '{"streams":[{"codec_name":"%s","width":%d,"height":%d}],"format":{"duration":"%s"}}' % (
        codec, width, height, duration)


class FfmpegBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = RecordingConfig(record_fps=15.0, bitrate_mbps=1.0, encoder="ffmpeg-libx264")
        self.backend = FfmpegSegmentBackend(self.config)
        self.partial = Path(self.temp.name) / "seg.mp4.partial"
        self.final = Path(self.temp.name) / "seg.mp4"
        self.metadata = {"segment_id": "seg", "relpath": "recordings/2026-10-22/seg.mp4",
                         "shape": (480, 640, 3), "format": "B"}

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, proc, probe):
        self.backend._width, self.backend._height = 640, 480
        self.backend._partial, self.backend._final = self.partial, self.final
        self.backend._metadata = self.metadata
        self.backend._proc = proc
        self.partial.write_bytes(b"x" * 32)
        return patch.object(subprocess, "run",
                            return_value=SimpleNamespace(returncode=0, stdout=probe))

    def test_command_declares_mp4_muxer_for_partial_suffix(self):
        self.backend._width, self.backend._height = 640, 480
        self.backend._partial = self.partial
        command = self.backend.command()
        last_output_format = len(command) - 1 - command[::-1].index("-f")
        self.assertEqual(command[last_output_format + 1], "mp4")
        self.assertLess(last_output_format, command.index(str(self.partial)))
        self.assertIn("640x480", command)
        self.assertIn("15.0", command)

    def test_start_requires_frame_shape(self):
        with self.assertRaises(FfmpegBackendError):
            self.backend.start(self.partial, self.final, {"relpath": "x"})

    def test_finish_publishes_only_after_probe_accepts_media(self):
        proc = FakeProc()
        with self.prepare(proc, probe_json()) as run:
            artifact = self.backend.finish()
        self.assertTrue(run.called)
        self.assertTrue(artifact.verified)
        self.assertEqual(artifact.relpath, self.metadata["relpath"])
        self.assertAlmostEqual(artifact.duration_seconds, 3.0)
        self.assertTrue(self.final.exists())
        self.assertFalse(self.partial.exists())

    def test_finish_rejects_wrong_codec_and_keeps_partial(self):
        proc = FakeProc()
        with self.prepare(proc, probe_json(codec="hevc")):
            with self.assertRaises(FfmpegBackendError):
                self.backend.finish()
        self.assertTrue(self.partial.exists())
        self.assertFalse(self.final.exists())

    def test_finish_reports_encoder_failure_without_paths(self):
        proc = FakeProc(returncode=1, errors=b"Unknown encoder 'libx264'\n")
        with self.prepare(proc, probe_json()):
            with self.assertRaises(FfmpegBackendError) as caught:
                self.backend.finish()
        message = str(caught.exception)
        self.assertIn("encoder failed", message)
        self.assertNotIn(self.temp.name, message)

    def test_abort_kills_encoder_and_removes_partial(self):
        proc = FakeProc()
        self.prepare(proc, probe_json())
        self.backend.abort()
        self.assertTrue(proc.killed)
        self.assertFalse(self.partial.exists())

    def test_finish_drops_closed_stdin_before_communicate(self):
        """communicate() flushes a live stdin handle; that raises ValueError after close()."""
        proc = FakeProc()
        with self.prepare(proc, probe_json()):
            self.backend.finish()
        self.assertIsNone(proc.stdin)

    def test_write_packet_uses_packed_bytes(self):
        proc = FakeProc()
        self.prepare(proc, probe_json())
        written = []
        proc.stdin.write = written.append
        self.backend.write(FramePacket(b"\x01\x02", 0.0, 0.0, 1, (1, 2, 1), "B"))
        self.assertEqual(written, [b"\x01\x02"])


if __name__ == "__main__":
    unittest.main()
