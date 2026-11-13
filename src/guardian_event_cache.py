"""Event-triggered clip cache: bounded pre-roll ring plus one clip per episode.

This module decides only WHEN to record and WHICH frames belong to a clip.  It
reuses :class:`guardian_recording.RecordingManager` for queueing, storage checks,
backend invocation and artifact verification, so the encoder contract stays
identical to the continuous recorder.

Integration contract:

* ``submit_frame`` is called from the unique camera capture point.  While idle it
  keeps a bounded ring of recent frames; while recording it appends the frame to
  the active clip.  It never encodes or touches the disk.
* ``trigger`` is called from the alert path (fall / sit / stranger).  It writes
  the event row, snapshots the pre-roll ring and arms a post-roll deadline.
* When the deadline expires the clip is finalized by ``RecordingManager`` and the
  event row is linked to the resulting ``recordings.id``.

No camera, ACL or encoder is imported here; a real ``backend_factory`` must be
supplied by the caller exactly as for continuous recording.
"""

from collections import deque
from dataclasses import dataclass, field, replace
import math
import threading
import time

from guardian_recording import FramePacket, RecordingManager

_IDLE = "idle"
_RECORDING = "recording"
_STOPPED = "stopped"


@dataclass
class _Clip:
    event_ids: list
    started_monotonic: float
    deadline_monotonic: float
    pending: deque = field(default_factory=deque)
    pending_bytes: int = 0
    manager: object = None
    recording_id: str = None
    pre_roll_frames: int = 0
    capped: bool = False
    failed: str = None


class _CapturingBackend:
    """Delegating backend that reports the segment id chosen by the manager."""

    def __init__(self, inner, on_open):
        self._inner = inner
        self._on_open = on_open

    def start(self, partial_path, final_path, metadata):
        self._inner.start(partial_path, final_path, metadata)
        self._on_open(metadata.get("segment_id"), metadata.get("relpath"))

    def write(self, packet):
        return self._inner.write(packet)

    def finish(self):
        return self._inner.finish()

    def abort(self):
        return self._inner.abort()


class _CapturingFactory:
    def __init__(self, factory, on_open):
        self._factory = factory
        self._on_open = on_open

    def __call__(self, config):
        return _CapturingBackend(self._factory(config), self._on_open)


class EventClipCache:
    """One worker thread; the ring is memory-only and strictly bounded."""

    def __init__(self, config, store, backend_factory,
                 clock=time.time, monotonic=time.monotonic, on_clip_ready=None):
        self.config = config
        self.store = store
        self._factory = backend_factory
        self._clock = clock
        self._monotonic = monotonic
        self._on_clip_ready = on_clip_ready
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._worker = None
        self._state = _STOPPED
        self._buffer = deque()
        self._buffer_bytes = 0
        self._clip = None
        self._max_frames = int(math.ceil(config.pre_roll_seconds * config.record_fps)) + 2
        self._accepted = self._dropped = self._completed = 0
        self._rejected = {}
        self._last_clip = None

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        with self._lock:
            if not self.config.enabled:
                self._state = _STOPPED
                return False
            if self._factory is None or self.store is None:
                self._state = _STOPPED
                return False
            if self._worker is not None and self._worker.is_alive():
                return True
            self._stop.clear()
            self._state = _IDLE
            self._worker = threading.Thread(target=self._run, name="guardian-event-cache",
                                            daemon=True)
            worker = self._worker
        try:
            worker.start()
        except Exception:
            with self._lock:
                self._worker = None
                self._state = _STOPPED
            return False
        return True

    def stop(self, timeout=15.0):
        with self._lock:
            worker = self._worker
            if worker is None:
                return True
            self._stop.set()
            self._wake.set()
        worker.join(float(timeout))
        with self._lock:
            alive = worker.is_alive()
            if not alive:
                self._worker = None
                self._state = _STOPPED
            return not alive

    # ------------------------------------------------------------------ ingest
    def submit_frame(self, frame, captured_at=None, monotonic_at=None, frame_id=None):
        """Copy at most one bounded frame; never blocks on IO or encoding."""
        if not self.config.enabled:
            return False
        try:
            utc = float(self._clock() if captured_at is None else captured_at)
            mono = float(self._monotonic() if monotonic_at is None else monotonic_at)
            if not math.isfinite(utc) or not math.isfinite(mono):
                return self._reject("invalid_frame")
            view = memoryview(frame)
            if not view.c_contiguous or view.nbytes == 0:
                return self._reject("unsupported_frame")
            if view.itemsize != 1 or view.format not in ("B", "b", "c"):
                return self._reject("unsupported_frame")
            packet = FramePacket(view.tobytes(), utc, mono, frame_id,
                                 tuple(view.shape), view.format)
        except Exception:
            return self._reject("invalid_frame")
        with self._lock:
            if self._stop.is_set():
                return self._reject("not_running")
            if self._clip is not None:
                self._clip.pending.append(packet)
                self._clip.pending_bytes += packet.nbytes
                self._trim_pending()
                self._accepted += 1
                self._wake.set()
                return True
            self._buffer.append(packet)
            self._buffer_bytes += packet.nbytes
            self._trim_buffer()
            self._accepted += 1
            return True

    def _reject(self, reason):
        with self._lock:
            self._dropped += 1
            self._rejected[reason] = self._rejected.get(reason, 0) + 1
        return False

    def _trim_buffer(self):
        # Caller holds the lock.
        while self._buffer and (len(self._buffer) > self._max_frames
                                or self._buffer_bytes > self.config.cache_bytes):
            dropped = self._buffer.popleft()
            self._buffer_bytes -= dropped.nbytes
            self._dropped += 1
            self._rejected["pre_roll_evicted"] = self._rejected.get("pre_roll_evicted", 0) + 1

    def _trim_pending(self):
        # Caller holds the lock.
        while self._clip.pending and self._clip.pending_bytes > self.config.cache_bytes:
            dropped = self._clip.pending.popleft()
            self._clip.pending_bytes -= dropped.nbytes
            self._dropped += 1
            self._rejected["clip_overflow"] = self._rejected.get("clip_overflow", 0) + 1

    # ----------------------------------------------------------------- trigger
    def trigger(self, kind=None, event_id=None, person_id=None, payload=None, at=None):
        """Arm or extend a clip.  Creates the event row when ``event_id`` is None."""
        if not self.config.enabled:
            return None
        if event_id is None:
            if kind is None:
                raise ValueError("trigger requires kind or event_id")
            event_id = self.store.add_event(
                kind, self._clock() if at is None else at,
                person_id=person_id, payload=payload)
        now_mono = float(self._monotonic())
        now_utc = float(self._clock() if at is None else at)
        with self._lock:
            clip = self._clip
            if clip is None:
                cutoff = now_utc - self.config.pre_roll_seconds
                snapshot = [packet for packet in self._buffer if packet.captured_at >= cutoff]
                self._buffer.clear()
                self._buffer_bytes = 0
                clip = _Clip(event_ids=[event_id], started_monotonic=now_mono,
                             deadline_monotonic=now_mono + self.config.post_roll_seconds,
                             pre_roll_frames=len(snapshot))
                clip.pending.extend(snapshot)
                clip.pending_bytes = sum(packet.nbytes for packet in snapshot)
                self._clip = clip
                self._wake.set()
                return {"event_id": event_id, "state": _RECORDING, "extended": False,
                        "pre_roll_frames": len(snapshot)}
            if event_id not in clip.event_ids:
                clip.event_ids.append(event_id)
            limit = clip.started_monotonic + self.config.event_clip_max_seconds
            proposed = now_mono + self.config.post_roll_seconds
            if proposed > limit:
                clip.capped = True
                proposed = limit
            if proposed > clip.deadline_monotonic:
                clip.deadline_monotonic = proposed
            self._wake.set()
            return {"event_id": event_id, "state": _RECORDING, "extended": True,
                    "event_count": len(clip.event_ids), "capped": clip.capped}

    # ------------------------------------------------------------------ status
    def status(self):
        with self._lock:
            clip = self._clip
            return {
                "state": self._state,
                "enabled": bool(self.config.enabled),
                "worker_alive": self._worker is not None and self._worker.is_alive(),
                "pre_roll_frames_cached": len(self._buffer),
                "pre_roll_bytes_cached": self._buffer_bytes,
                "pre_roll_seconds": self.config.pre_roll_seconds,
                "post_roll_seconds": self.config.post_roll_seconds,
                "active_clip": None if clip is None else {
                    "event_count": len(clip.event_ids),
                    "recording_id": clip.recording_id,
                    "pre_roll_frames": clip.pre_roll_frames,
                    "pending_frames": len(clip.pending),
                    "capped": clip.capped,
                    "failed": clip.failed,
                },
                "accepted_frames": self._accepted,
                "dropped_frames": self._dropped,
                "completed_clips": self._completed,
                "drop_reasons": dict(self._rejected),
                "last_clip": self._last_clip,
            }

    # ------------------------------------------------------------------ worker
    def _run(self):
        try:
            while True:
                with self._lock:
                    clip = self._clip
                    stopping = self._stop.is_set()
                if clip is None:
                    if stopping:
                        break
                    self._wake.wait(0.1)
                    self._wake.clear()
                    continue
                if clip.manager is None and clip.failed is None:
                    self._open_clip(clip)
                packet = self._next_packet(clip)
                if packet is not None:
                    self._submit(clip, packet)
                    continue
                with self._lock:
                    deadline = clip.deadline_monotonic
                    pending = len(clip.pending)
                if pending == 0 and (stopping or self._monotonic() >= deadline):
                    self._finish_clip(clip)
                    continue
                self._wake.wait(0.05)
                self._wake.clear()
        finally:
            with self._lock:
                self._clip = None
                self._state = _STOPPED

    def _open_clip(self, clip):
        """Start a dedicated manager so one episode maps to one recording row."""
        span = min(self.config.event_clip_max_seconds + 5, 3600)
        clip_config = replace(
            self.config, enabled=True, segment_seconds=max(1, int(span)),
            queue_frames=max(self.config.queue_frames,
                             min(300, int(math.ceil(self.config.record_fps * 2)) + 1)))
        manager = RecordingManager(clip_config, store=self.store,
                                   backend_factory=_CapturingFactory(self._factory,
                                                                     self._bind_recording),
                                   clock=self._clock, monotonic=self._monotonic)
        if not manager.start():
            with self._lock:
                clip.failed = manager.status().get("error") or "clip_manager_start_failed"
                count = len(clip.pending)
                clip.pending.clear()
                clip.pending_bytes = 0
                self._dropped += count
                self._rejected[clip.failed] = self._rejected.get(clip.failed, 0) + count
            return
        clip.manager = manager

    def _bind_recording(self, segment_id, relpath):
        with self._lock:
            if self._clip is not None:
                self._clip.recording_id = segment_id

    def _next_packet(self, clip):
        with self._lock:
            if not clip.pending:
                return None
            packet = clip.pending.popleft()
            clip.pending_bytes -= packet.nbytes
            return packet

    def _submit(self, clip, packet):
        """Blocking retry: a dropped pre-roll frame is a lost part of the clip."""
        deadline = time.monotonic() + 3.0
        while True:
            if self._stop.is_set():
                break
            frame = packet.data
            try:
                if packet.shape and len(packet.shape) > 1:
                    frame = memoryview(packet.data).cast("B", shape=packet.shape)
            except (TypeError, ValueError):
                frame = packet.data
            if clip.manager.submit_frame(frame, captured_at=packet.captured_at,
                                         monotonic_at=packet.monotonic_at,
                                         frame_id=packet.frame_id):
                return True
            if time.monotonic() >= deadline:
                break
            time.sleep(0.005)
        with self._lock:
            self._dropped += 1
            self._rejected["clip_submit_failed"] = self._rejected.get("clip_submit_failed", 0) + 1
        return False

    def _finish_clip(self, clip):
        manager = clip.manager
        stopped = manager.stop(timeout=15.0) if manager is not None else False
        state = manager.status() if manager is not None else {}
        completed = stopped and state.get("state") == "stopped" and state.get("completed_segments")
        linked = 0
        if completed and clip.recording_id:
            for event_id in clip.event_ids:
                try:
                    self.store.link_event_recording(event_id, clip.recording_id)
                    linked += 1
                except Exception:
                    pass
        with self._lock:
            self._completed += 1
            self._last_clip = {
                "recording_id": clip.recording_id,
                "event_ids": list(clip.event_ids),
                "linked_events": linked,
                "pre_roll_frames": clip.pre_roll_frames,
                "finalized": bool(completed),
                "capped": clip.capped,
                "failed": clip.failed,
                "manager_state": state.get("state"),
                "written_frames": state.get("written_frames"),
            }
            self._clip = None
        if completed and clip.recording_id and callable(self._on_clip_ready):
            try:
                self._on_clip_ready(list(clip.event_ids), clip.recording_id)
            except Exception:
                pass
