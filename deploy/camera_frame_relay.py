"""Share one board MJPEG connection; clients read a bounded latest-frame slot.

Only JPEG bytes live in RAM. No files, identities, recognition or recording changes.
"""
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import time

MAX_FRAME_BYTES = 1024 * 1024


class JpegParser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk):
        self.buffer.extend(chunk)
        latest = None
        while True:
            start = self.buffer.find(b'\xff\xd8')
            if start < 0:
                self.buffer[:] = self.buffer[-1:]
                break
            end = self.buffer.find(b'\xff\xd9', start + 2)
            if end < 0:
                del self.buffer[:start]
                if len(self.buffer) > MAX_FRAME_BYTES:
                    raise ValueError('frame exceeds limit')
                break
            if end + 2 - start > MAX_FRAME_BYTES:
                raise ValueError('frame exceeds limit')
            latest = bytes(self.buffer[start:end + 2])
            del self.buffer[:end + 2]
        return latest


class LatestFrame:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.frame = None
        self.received_at = 0.0
        self.sequence = 0

    def publish(self, frame):
        with self.lock:
            self.frame = frame
            self.received_at = self.clock()
            self.sequence += 1

    def clear(self):
        with self.lock:
            self.frame = None

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
            last_frame_at = time.monotonic()
            while not stop.is_set():
                chunk = response.read1(65536)
                if not chunk:
                    raise OSError('source closed')
                frame = parser.feed(chunk)
                if frame is not None:
                    slot.publish(frame)
                    last_frame_at = time.monotonic()
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
