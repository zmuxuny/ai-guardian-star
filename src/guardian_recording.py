"""Opt-in, bounded recording worker; no camera/ACL/encoder is selected here.

This module is a preparation layer, not a working video encoder.  The board must
provide a tested backend_factory(config).  Each backend instance records ONE
segment and implements:

    start(partial_path: Path, final_path: Path, metadata: dict) -> None
    write(packet: FramePacket) -> None
    finish() -> SegmentArtifact
    abort() -> None

The backend owns container finalization, bounded IO timeouts, media probing,
flush/fsync policy and final publication. finish() must return verified=True
ONLY after validating the actual encoded media and its timestamps. A rename
alone is insufficient. abort() must be bounded; unfinished files stay partial.
FramePacket.data is a private immutable byte copy, packed in C order, with the
source shape/format and original UTC/monotonic timestamps. The backend must use
those timestamps, not invent missing frames from nominal record_fps.

No real backend is shipped. Fake backends used in tests do not prove MP4
playability, media correctness, encoding speed, or board recording readiness.
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from pathlib import Path
import shutil
import threading
import time
import uuid


@dataclass(frozen=True)
class FramePacket:
    data: bytes
    captured_at: float
    monotonic_at: float
    frame_id: object
    shape: tuple
    format: str

    @property
    def nbytes(self):
        return len(self.data)


@dataclass(frozen=True)
class SegmentArtifact:
    """A backend's explicit verification result, rechecked against local file."""

    relpath: str
    size_bytes: int
    verified: bool
    duration_seconds: float = 0.0


@dataclass(frozen=True)
class _FrameTime:
    captured_at: float
    monotonic_at: float


class _RecordingFault(RuntimeError):
    pass


class RecordingManager:
    """A one-shot session, accepting contiguous byte buffers without blocking IO.

    submit_frame is intended for the unique camera's successful capture point.
    It never encodes, writes files, or calls the store. It copies at most one
    bounded frame. The caller may immediately reuse its input buffer. Frames
    waiting AND being encoded count towards both memory limits. Unsupported,
    oversized, busy and full submissions return False and are counted.

    A backend may block only its worker: stop(timeout) reports stop_timeout while
    that worker remains alive. Python cannot forcibly cancel arbitrary backend
    code, so a tested backend must supply its own IO/process deadlines.

    Storage marker identity is checked before each write. Full usage/free-space
    checks run at segment boundaries and at most once per second between them,
    with raw-input byte reservations between scans. This is a stop threshold,
    NOT a strict on-disk quota: backend buffering/encoding overhead or another
    writer can exceed this estimate. A real backend must bound its output and
    leave headroom; board tests must measure that headroom.
    """

    def __init__(self, config, store=None, backend_factory=None,
                 clock=time.time, monotonic=time.monotonic):
        self.config = config
        self.store = store
        self._factory = backend_factory
        self._clock = clock
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._queue = deque()
        self._worker = None
        self._state = "disabled" if not config.enabled else "prepared"
        self._error = None
        self._accepted = self._written = self._dropped = 0
        self._rejected = {}
        self._bytes = self._frames = 0
        self._inflight_bytes = 0
        self._copying = 0
        self._active_segment = None
        self._segment_relpath = None
        self._completed_segments = 0
        self._pending_gap = None
        self._session_id = uuid.uuid4().hex
        self._space_check_at = None
        self._space_used = self._space_free = self._space_reserved = 0

    def start(self):
        """Start only with explicit store, encoder, backend and managed storage."""
        with self._lock:
            if not self.config.enabled:
                return False
            if self._worker is not None:
                return self._worker.is_alive() and not self._stop.is_set()
            if not self.config.encoder or self._factory is None:
                self._state = "awaiting_encoder"
                self._error = "待上板选择并验证编码器和录像后端"
                return False
            if self.store is None:
                self._state = "awaiting_storage"
                self._error = "需要显式初始化的受管存储及 HistoryStore"
                return False
            try:
                self._check_storage(force=True)
            except Exception as exc:
                self._state = "failed"
                self._error = self._describe(exc)
                return False
            self._state = "running"
            self._error = None
            self._worker = threading.Thread(target=self._run,
                                            name="guardian-recording", daemon=True)
            try:
                self._worker.start()
            except Exception as exc:
                self._worker = None
                self._state = "failed"
                self._error = self._describe(exc)
                return False
            return True

    def _reject(self, reason, captured_at=None):
        with self._lock:
            self._dropped += 1
            self._rejected[reason] = self._rejected.get(reason, 0) + 1
            if captured_at is not None:
                previous = self._pending_gap
                self._pending_gap = ((captured_at, captured_at, reason) if previous is None
                                     else (min(previous[0], captured_at),
                                           max(previous[1], captured_at), "frame_drops"))
                self._wake.set()
        return False

    def submit_frame(self, frame, captured_at=None, monotonic_at=None, frame_id=None):
        if not self.config.enabled:
            return False
        if self._state != "running" or self._stop.is_set():
            return self._reject("not_running")
        try:
            utc = float(self._clock() if captured_at is None else captured_at)
            mono = float(self._monotonic() if monotonic_at is None else monotonic_at)
            if not math.isfinite(utc) or not math.isfinite(mono):
                raise ValueError("nonfinite capture time")
            view = memoryview(frame)
            if not view.c_contiguous or view.nbytes == 0:
                return self._reject("unsupported_frame", utc)
            # No object pointers or multi-byte native interpretation at this API.
            if view.itemsize != 1 or view.format not in ("B", "b", "c"):
                return self._reject("unsupported_frame", utc)
            size = view.nbytes
        except Exception:
            return self._reject("invalid_frame")
        if size > self.config.queue_bytes:
            return self._reject("oversized_frame", utc)
        with self._lock:
            if self._state != "running" or self._stop.is_set():
                return self._reject("not_running")
            if (self._frames >= self.config.queue_frames or
                    self._bytes + size > self.config.queue_bytes):
                return self._reject("queue_full", utc)
            self._frames += 1
            self._bytes += size
            self._copying += 1
        try:
            # Reservation counts concurrent copies before releasing the lock.
            # Large copies never prevent the worker from advancing its queue.
            if frame_id is not None and (type(frame_id) not in (int, str) or
                                         len(str(frame_id)) > 128):
                raise ValueError("invalid frame id")
            packet = FramePacket(view.tobytes(), utc, mono, frame_id,
                                 tuple(view.shape), view.format)
        except Exception:
            with self._lock:
                self._bytes -= size
                self._frames -= 1
                self._copying -= 1
                self._wake.set()
            return self._reject("copy_failed", utc)
        with self._lock:
            self._copying -= 1
            if self._state != "running" or self._stop.is_set():
                self._bytes -= size
                self._frames -= 1
                self._wake.set()
                return self._reject("not_running")
            self._queue.append(packet)
            self._accepted += 1
            self._wake.set()
            return True

    def stop(self, timeout=5.0):
        """Stop accepting; drain queued frames, finalize, and wait at most timeout."""
        timeout = float(timeout)
        if not math.isfinite(timeout) or timeout < 0:
            raise ValueError("stop timeout must be finite and nonnegative")
        with self._lock:
            worker = self._worker
            if worker is None:
                return True
            self._stop.set()
            if worker.is_alive() and self._state != "failed":
                self._state = "stopping"
            self._wake.set()
        worker.join(timeout)
        with self._lock:
            if worker.is_alive():
                self._state = "stop_timeout"
                self._error = "录像后端仍在运行，未确认封装或退出"
                return False
            return True

    def status(self):
        with self._lock:
            alive = self._worker is not None and self._worker.is_alive()
            return {"state": self._state, "enabled": bool(self.config.enabled),
                    "backend_configured": self._factory is not None,
                    "worker_alive": alive, "accepting": self._state == "running",
                    "accepted_frames": self._accepted, "written_frames": self._written,
                    "dropped_frames": self._dropped, "drop_reasons": dict(self._rejected),
                    "queued_frames": len(self._queue),
                    "buffered_frames": self._frames, "buffered_bytes": self._bytes,
                    "inflight_bytes": self._inflight_bytes,
                    "copying_frames": self._copying,
                    "active_segment": self._active_segment,
                    "completed_segments": self._completed_segments, "error": self._error,
                    "real_encoder_verified": False}

    @staticmethod
    def _describe(exc):
        # Avoid exception text containing host paths, subprocess arguments or secrets.
        return str(exc) if isinstance(exc, _RecordingFault) else type(exc).__name__

    def _check_storage(self, reserve_bytes=0, force=False):
        from guardian_storage import validate_storage
        validate_storage(self.config)
        now = self._monotonic()
        if (force or self._space_check_at is None or
                now - self._space_check_at >= 1 or now < self._space_check_at):
            self._space_used = self.store.managed_size_bytes()
            self._space_free = shutil.disk_usage(self.config.data_root).free
            self._space_reserved = 0
            self._space_check_at = now
        if self._space_used + self._space_reserved + reserve_bytes >= self.config.storage_quota_bytes:
            raise _RecordingFault("storage_quota_exhausted")
        if self._space_free - self._space_reserved - reserve_bytes < self.config.min_free_bytes:
            raise _RecordingFault("storage_minimum_free_reached")

    def _flush_gap(self):
        with self._lock:
            gap, self._pending_gap = self._pending_gap, None
        if gap is not None:
            self.store.add_gap(gap[0], gap[1], gap[2])

    def _run(self):
        backend = None
        segment = None
        first = last = None
        date = None
        shape = pixel_format = None
        failure = None
        try:
            # Config deliberately supports Asia/Shanghai only; avoid requiring
            # an extra tzdata package on Windows/offline board environments.
            if self.config.timezone != "Asia/Shanghai":
                raise ValueError("unsupported recording timezone")
            zone = timezone(timedelta(hours=8), "Asia/Shanghai")
            while True:
                with self._lock:
                    packet = self._queue.popleft() if self._queue else None
                    if packet is None:
                        self._wake.clear()
                    else:
                        self._inflight_bytes = packet.nbytes
                self._flush_gap()
                if packet is None:
                    if self._stop.is_set() and self._copying == 0:
                        break
                    self._wake.wait(0.2)
                    continue
                try:
                    self._check_storage(packet.nbytes)
                    packet_date = datetime.fromtimestamp(packet.captured_at, zone).date()
                    discontinuity = (last is not None and
                                     (packet.monotonic_at <= last.monotonic_at or
                                      abs((packet.captured_at - last.captured_at) -
                                          (packet.monotonic_at - last.monotonic_at)) > 2))
                    rotate = (backend is not None and
                              (packet.monotonic_at - first >= self.config.segment_seconds
                               or packet_date != date or discontinuity
                               or packet.shape != shape or packet.format != pixel_format))
                    if rotate:
                        self._finish(backend, segment, last)
                        backend = segment = None
                        if discontinuity:
                            self.store.add_gap(min(last.captured_at, packet.captured_at),
                                               max(last.captured_at, packet.captured_at),
                                               "capture_clock_discontinuity")
                    if backend is None:
                        from guardian_storage import safe_managed_path
                        segment = uuid.uuid4().hex
                        relpath = "recordings/{}/{}.mp4".format(packet_date, segment)
                        self._segment_relpath = relpath
                        final_path = safe_managed_path(self.config, relpath)
                        final_path.parent.mkdir(parents=True, exist_ok=True)
                        # Revalidate after directory creation, before a backend writes.
                        self._check_storage(packet.nbytes, force=True)
                        safe_managed_path(self.config, relpath)
                        self.store.start_segment(segment, relpath + ".partial", packet.captured_at,
                                                 session_id=self._session_id,
                                                 monotonic_start=packet.monotonic_at,
                                                 encoder=self.config.encoder, shape=packet.shape,
                                                 nominal_fps=self.config.record_fps)
                        backend = self._factory(self.config)
                        backend.start(Path(str(final_path) + ".partial"), final_path,
                                      {"segment_id": segment, "relpath": relpath,
                                       "captured_at": packet.captured_at,
                                       "monotonic_at": packet.monotonic_at,
                                       "shape": packet.shape, "format": packet.format})
                        first, date = packet.monotonic_at, packet_date
                        shape, pixel_format = packet.shape, packet.format
                        with self._lock:
                            self._active_segment = segment
                    backend.write(packet)
                    self._space_reserved += packet.nbytes
                    last = _FrameTime(packet.captured_at, packet.monotonic_at)
                    with self._lock:
                        self._written += 1
                finally:
                    with self._lock:
                        self._frames -= 1
                        self._bytes -= packet.nbytes
                        self._inflight_bytes = 0
                packet = None
            if backend is not None:
                self._finish(backend, segment, last)
                backend = segment = None
            self._flush_gap()
        except Exception as exc:
            failure = self._describe(exc)
            self._stop.set()
            with self._lock:
                self._state = "failed"
                self._error = failure
            if segment is not None:
                try:
                    self.store.fail_segment(segment, failure)
                except Exception:
                    pass
            try:
                now = self._clock()
                self.store.add_gap(last.captured_at if last else now, now,
                                   "recording_worker_failed:" + failure)
            except Exception:
                pass
            if backend is not None:
                try:
                    backend.abort()
                except Exception:
                    pass
        finally:
            with self._lock:
                discarded = len(self._queue)
                self._dropped += discarded
                if discarded:
                    self._rejected["worker_stopped"] = discarded
                # Concurrent copies retain reservations until they observe stop.
                queued_bytes = sum(item.nbytes for item in self._queue)
                self._queue.clear()
                self._bytes = max(0, self._bytes - queued_bytes - self._inflight_bytes)
                self._frames = max(0, self._frames - discarded - bool(self._inflight_bytes))
                self._inflight_bytes = 0
                self._active_segment = None
                self._state = "failed" if failure else "stopped"
                if not failure:
                    self._error = None

    def _finish(self, backend, segment, last):
        from guardian_storage import safe_managed_path
        self._check_storage(force=True)
        artifact = backend.finish()
        if not isinstance(artifact, SegmentArtifact) or not artifact.verified:
            raise ValueError("backend did not verify encoded media")
        if (not isinstance(artifact.size_bytes, int) or artifact.size_bytes <= 0 or
                not math.isfinite(artifact.duration_seconds) or artifact.duration_seconds < 0):
            raise ValueError("invalid artifact result")
        if artifact.relpath != self._segment_relpath:
            raise ValueError("artifact identity mismatch")
        path = safe_managed_path(self.config, artifact.relpath, must_exist=True)
        if not path.is_file() or path.stat().st_size != artifact.size_bytes:
            raise ValueError("artifact size mismatch")
        self._check_storage(force=True)
        self.store.finish_segment(segment, last.captured_at, artifact.size_bytes,
                                  relpath=artifact.relpath, monotonic_end=last.monotonic_at,
                                  duration_seconds=artifact.duration_seconds, media_verified=True)
        with self._lock:
            self._completed_segments += 1
            self._active_segment = None
