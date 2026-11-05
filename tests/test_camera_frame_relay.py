import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
from camera_frame_relay import JpegParser, LatestFrame, PreviewHandler, MAX_FRAME_BYTES


class RelayTests(unittest.TestCase):
    def test_fragmented_markers_and_coalesced_frames_keep_latest(self):
        parser = JpegParser()
        self.assertIsNone(parser.feed(b'--frame\r\n\xff'))
        self.assertIsNone(parser.feed(b'\xd8first\xff'))
        self.assertEqual(parser.feed(b'\xd9\r\n\xff\xd8second\xff\xd9tail'), b'\xff\xd8second\xff\xd9')
        self.assertLessEqual(len(parser.buffer), 1)

    def test_malformed_frame_cannot_grow_memory_forever(self):
        parser = JpegParser()
        with self.assertRaises(ValueError):
            parser.feed(b'\xff\xd8' + b'x' * MAX_FRAME_BYTES)

    def test_latest_slot_drops_history_and_expires_without_new_source_frames(self):
        now = [10.0]
        slot = LatestFrame(lambda: now[0])
        for index in range(100):
            slot.publish(str(index).encode())
        self.assertEqual(slot.read()[:2], (b'99', 100))
        now[0] += 1.6
        self.assertIsNone(slot.read()[0])
        slot.publish(b'new')
        slot.clear()
        self.assertIsNone(slot.read()[0])

    def test_many_http_reads_share_the_same_latest_slot_and_stale_is_204(self):
        slot = LatestFrame()
        slot.publish(b'\xff\xd8test\xff\xd9')
        server = ThreadingHTTPServer(('127.0.0.1', 0), PreviewHandler)
        server.latest = slot
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        conn = http.client.HTTPConnection(*server.server_address, timeout=2)
        try:
            for _ in range(5):
                conn.request('GET', '/video_frame?t=1')
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(response.getheader('X-Camera-Sequence'), '1')
                self.assertEqual(response.read(), b'\xff\xd8test\xff\xd9')
            slot.clear()
            conn.request('GET', '/video_frame')
            response = conn.getresponse()
            self.assertEqual(response.status, 204)
            self.assertEqual(response.read(), b'')
        finally:
            conn.close()
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
