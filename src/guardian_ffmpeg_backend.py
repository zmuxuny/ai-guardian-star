"""Real ffmpeg/libx264 segment backend for RecordingManager and EventClipCache.

The recording manager always hands a ``<name>.mp4.partial`` path, so the
container is passed explicitly with ``-f mp4``: ffmpeg cannot infer a muxer from
that suffix and exits immediately with a broken pipe.

Frames arrive as packed BGR bytes (OpenCV layout) and are verified with ffprobe
before the partial file is published as the final MP4.  Nothing here imports
OpenCV, ACL or the camera.
"""

import json
import os
import subprocess

from guardian_recording import SegmentArtifact


class FfmpegBackendError(RuntimeError):
    """Raised with a message that never contains device paths or tokens."""


class FfmpegSegmentBackend:
    """One instance records exactly one segment, per the manager contract."""

    def __init__(self, config, pixel_format="bgr24", preset="veryfast",
                 finish_timeout=30.0, probe_timeout=20.0):
        self.config = config
        self.pixel_format = pixel_format
        self.preset = preset
        self.finish_timeout = float(finish_timeout)
        self.probe_timeout = float(probe_timeout)
        self._proc = None
        self._partial = None
        self._final = None
        self._metadata = None
        self._width = 0
        self._height = 0
        self._frames = 0

    def command(self):
        bitrate = float(self.config.bitrate_mbps)
        return [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-f", "rawvideo", "-pix_fmt", self.pixel_format,
            "-s", "{}x{}".format(self._width, self._height),
            "-r", str(self.config.record_fps), "-i", "pipe:0",
            "-c:v", "libx264", "-preset", self.preset, "-pix_fmt", "yuv420p",
            "-b:v", "{:g}M".format(bitrate),
            "-movflags", "+faststart", "-f", "mp4", str(self._partial),
        ]

    def start(self, partial_path, final_path, metadata):
        shape = tuple(metadata.get("shape") or ())
        if len(shape) < 2:
            raise FfmpegBackendError("frame shape unavailable")
        self._height, self._width = int(shape[0]), int(shape[1])
        if self._width <= 0 or self._height <= 0:
            raise FfmpegBackendError("invalid frame size")
        self._partial = partial_path
        self._final = final_path
        self._metadata = metadata
        self._frames = 0
        self._proc = subprocess.Popen(
            self.command(), stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def write(self, packet):
        if self._proc is None or self._proc.stdin is None:
            raise FfmpegBackendError("encoder not started")
        try:
            self._proc.stdin.write(packet.data)
        except (BrokenPipeError, ValueError):
            raise FfmpegBackendError("encoder stopped accepting frames") from None
        self._frames += 1

    def finish(self):
        if self._proc is None:
            raise FfmpegBackendError("encoder not started")
        self._close_stdin()
        try:
            _, errors = self._proc.communicate(timeout=self.finish_timeout)
        except subprocess.TimeoutExpired:
            self.abort()
            raise FfmpegBackendError("encoder finish timeout") from None
        if self._proc.returncode != 0:
            detail = (errors or b"").decode("utf-8", "replace").strip().splitlines()
            raise FfmpegBackendError("encoder failed: " + (detail[-1] if detail else "unknown"))
        duration = self._probe_duration()
        os.replace(str(self._partial), str(self._final))
        return SegmentArtifact(self._metadata["relpath"],
                               os.path.getsize(str(self._final)), True, duration)

    def _close_stdin(self):
        """Send EOF, then drop the handle: communicate() must not flush a closed pipe.

        Popen.communicate() flushes an existing stdin handle and does not catch
        ValueError, so leaving it in place after close() makes the whole segment
        fail even though the encoder exited cleanly.
        """
        stream = self._proc.stdin
        if stream is None:
            return
        try:
            stream.close()
        except (BrokenPipeError, ValueError, OSError):
            pass
        self._proc.stdin = None

    def _probe_duration(self):
        try:
            done = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_name,width,height",
                 "-show_entries", "format=duration", "-of", "json", str(self._partial)],
                capture_output=True, text=True, timeout=self.probe_timeout)
        except (OSError, subprocess.SubprocessError):
            raise FfmpegBackendError("media probe failed") from None
        if done.returncode != 0:
            raise FfmpegBackendError("media probe rejected the file")
        try:
            info = json.loads(done.stdout)
            stream = info["streams"][0]
            duration = float(info["format"]["duration"])
        except (KeyError, IndexError, TypeError, ValueError):
            raise FfmpegBackendError("media probe returned no usable stream") from None
        if stream.get("codec_name") != "h264":
            raise FfmpegBackendError("unexpected codec")
        if int(stream.get("width", 0)) != self._width or int(stream.get("height", 0)) != self._height:
            raise FfmpegBackendError("unexpected resolution")
        if not duration > 0:
            raise FfmpegBackendError("nonpositive duration")
        return duration

    def abort(self):
        proc = self._proc
        if proc is not None and proc.poll() is None:
            try:
                self._close_stdin()
            except AttributeError:
                pass
            try:
                proc.kill()
            except OSError:
                pass
            try:
                proc.communicate(timeout=5)
            except (subprocess.SubprocessError, ValueError):
                pass
        if self._partial is not None and os.path.exists(str(self._partial)):
            try:
                os.unlink(str(self._partial))
            except OSError:
                pass


def create_backend(config):
    """Default backend factory used by the service wiring."""
    return FfmpegSegmentBackend(config)
