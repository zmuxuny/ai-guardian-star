"""Share one board MJPEG connection; clients read a bounded latest-frame slot.

Only JPEG bytes live in RAM. No files, identities, recognition or recording changes.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import math
import re
import threading
import time

MAX_FRAME_BYTES = 1024 * 1024
MAX_BACKLOG_SECONDS = 0.75


class JpegParser:
    def __init__(self):
        self.buffer = bytearray()
        self.source_timestamp = None
        self._pending_timestamp = None
        self._in_frame = False

    def feed(self, chunk):
        self.buffer.extend(chunk)
        latest = None
        while True:
            start = self.buffer.find(b'\xff\xd8')
            if start < 0:
                # Retain bounded multipart headers split across network reads.
                self.buffer[:] = self.buffer[-4096:]
                break
            if not self._in_frame:
                match = re.search(rb'X-Camera-Captured-Monotonic:\s*([^\r\n]+)',
                                  self.buffer[:start], re.IGNORECASE)
                self._pending_timestamp = float(match[1]) if match else None
                if self._pending_timestamp is not None and not math.isfinite(self._pending_timestamp):
                    raise ValueError('invalid source timestamp')
                self._in_frame = True
            end = self.buffer.find(b'\xff\xd9', start + 2)
            if end < 0:
                del self.buffer[:start]
                if len(self.buffer) > MAX_FRAME_BYTES:
                    raise ValueError('frame exceeds limit')
                break
            if end + 2 - start > MAX_FRAME_BYTES:
                raise ValueError('frame exceeds limit')
            latest = bytes(self.buffer[start:end + 2])
            self.source_timestamp = self._pending_timestamp
            self._pending_timestamp = None
            self._in_frame = False
            del self.buffer[:end + 2]
        return latest


class StreamDelay:
    """Estimate added queue delay without synchronizing the two device clocks.

    The first/latest request sets a baseline; only growth above the best observed
    clock offset is detectable. It is not absolute capture-to-display latency.
    """
    def __init__(self):
        self.offset = None
        self.last_source = None

    def observe(self, source_timestamp, received_at):
        if source_timestamp is None:
            return 0.0  # Compatible with older boards without timestamp headers.
        if self.last_source is not None and source_timestamp <= self.last_source:
            raise ValueError('source clock reset or repeated frame')
        self.last_source = source_timestamp
        offset = received_at - source_timestamp
        self.offset = offset if self.offset is None else min(self.offset, offset)
        extra_delay = max(0.0, offset - self.offset)
        if extra_delay > MAX_BACKLOG_SECONDS:
            raise ValueError('source stream accumulated delay')
        return extra_delay


class LatestFrame:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.frame = None
        self.received_at = 0.0
        self.sequence = 0
        self.reconnects = 0

    def publish(self, frame, extra_delay=0.0):
        with self.lock:
            self.frame = frame
            self.received_at = self.clock() - extra_delay
            self.sequence += 1

    def clear(self):
        with self.lock:
            self.frame = None
            self.reconnects += 1

    def read(self):
        with self.lock:
            age = self.clock() - self.received_at
            if self.frame is None or age > 1.5:
                return None, self.sequence, age
            return self.frame, self.sequence, age


def receive_frames(slot, stop):
    while not stop.is_set():
        conn = http.client.HTTPConnection('127.0.0.1', 6001, timeout=3)
        try:
            conn.request('GET', '/video_feed', headers={'Cache-Control': 'no-cache'})
            response = conn.getresponse()
            if response.status != 200:
                raise OSError('source unavailable')
            parser = JpegParser()
            delay = StreamDelay()
            last_frame_at = time.monotonic()
            while not stop.is_set():
                chunk = response.read1(65536)
                if not chunk:
                    raise OSError('source closed')
                frame = parser.feed(chunk)
                if frame is not None:
                    received_at = time.monotonic()
                    extra_delay = delay.observe(parser.source_timestamp, received_at)
                    slot.publish(frame, extra_delay)
                    last_frame_at = received_at
                elif time.monotonic() - last_frame_at > 3:
                    raise OSError('source stalled')
        except (OSError, ValueError, http.client.HTTPException):
            slot.clear()
        finally:
            conn.close()
        stop.wait(0.5)


class PreviewHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def do_GET(self):
        if self.path.split('?', 1)[0] != '/video_frame':
            self.send_error(404)
            return
        frame, sequence, age = self.server.latest.read()
        self.send_response(200 if frame is not None else 204)
        self.send_header('Content-Length', str(len(frame) if frame is not None else 0))
        self.send_header('Cache-Control', 'no-store, no-cache, max-age=0')
        self.send_header('X-Camera-Sequence', str(sequence))
        self.send_header('X-Camera-Stream-Reconnects', str(self.server.latest.reconnects))
        self.send_header('X-Camera-Frame-Age-Ms', str(max(0, round(age * 1000))))
        if frame is not None:
            self.send_header('Content-Type', 'image/jpeg')
        self.end_headers()
        if frame is not None:
            try:
                self.wfile.write(frame)
            except OSError:
                pass

    def log_message(self, *_args):
        pass


def main():
    slot = LatestFrame()
    stop = threading.Event()
    server = ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('CAMERA_PREVIEW_PORT', '6011'))), PreviewHandler)
    server.latest = slot
    threading.Thread(target=receive_frames, args=(slot, stop), daemon=True).start()
    try:
        server.serve_forever()
    finally:
        stop.set()
        server.server_close()


if __name__ == '__main__':
    main()
