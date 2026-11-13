"""Sample the shared camera stream for independent continuous recording.

The encoder writes at a fixed nominal rate, so the sampler must keep the frame
count in step with the wall clock.  The capture loop does not deliver a frame
exactly every 1/fps seconds (inference, ACL and USB jitter all interfere); if we
forwarded only one frame per callback, a 60-second segment would carry far fewer
frames than 60 * fps and would play back faster than reality.  Measured on the
board: 7.35 fps delivered against 8 fps nominal produced a 55 s file for a 60 s
wall-clock span (ratio 0.919).

`repeats` re-sends the same frame for every missed slot, capped so that a long
stall does not burst a large batch into the recording queue at once.
"""

import threading

MAX_CATCH_UP_FRAMES = 4


class ContinuousCaptureSink:
    def __init__(self, manager, fps, max_width=640):
        self.manager = manager
        self.interval = 1.0 / float(fps)
        self.max_width = int(max_width)
        self._lock = threading.Lock()
        self._last_arrival = None
        self._virtual = None
        self._duplicated = 0

    def __call__(self, frame, captured_at, monotonic_at):
        with self._lock:
            # 1) 到达节流：贴着上一次"到达"判断，保持既有语义
            if (self._last_arrival is not None and
                    monotonic_at - self._last_arrival < self.interval * 0.9):
                return False
            self._last_arrival = monotonic_at
            # 2) 帧时间戳走虚拟采样时钟，落后墙钟时补帧
            if self._virtual is None:
                self._virtual = monotonic_at
                repeats = 1
            else:
                self._virtual += self.interval
                behind = int(round((monotonic_at - self._virtual) / self.interval))
                repeats = 1 + max(0, min(behind, MAX_CATCH_UP_FRAMES - 1))
                self._virtual += (repeats - 1) * self.interval
                if repeats > 1:
                    self._duplicated += repeats - 1
            base = self._virtual - (repeats - 1) * self.interval
        height, width = frame.shape[:2]
        if width > self.max_width:
            import cv2
            output_width = self.max_width - self.max_width % 2
            output_height = max(2, int(height * output_width / width) // 2 * 2)
            frame = cv2.resize(frame, (output_width, output_height), interpolation=cv2.INTER_AREA)
        accepted = False
        for index in range(repeats):
            # Each repeated frame gets its own strictly increasing timestamp.
            # Reusing one timestamp makes RecordingManager treat the repeats as
            # a clock discontinuity and rotate a sub-second segment.
            accepted = self.manager.submit_frame(
                frame, captured_at=captured_at,
                monotonic_at=base + index * self.interval)
        return accepted

    def status(self):
        with self._lock:
            return {"interval": self.interval, "duplicated_frames": self._duplicated}
