import http.client
from http.server import ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy'))
from camera_frame_relay import JpegParser, LatestFrame, PreviewHandler, MAX_FRAME_BYTES, StreamDelay, receive_frames


class RelayTests(unittest.TestCase):
    def test_fragmented_markers_and_coalesced_frames_keep_latest(self):
        parser = JpegParser()
        self.assertIsNone(parser.feed(b'--frame\r\n\xff'))
        self.assertIsNone(parser.feed(b'\xd8first\xff'))
        self.assertEqual(parser.feed(b'\xd9\r\n\xff\xd8second\xff\xd9tail'), b'\xff\xd8second\xff\xd9')
        self.assertLessEqual(len(parser.buffer), 4096)

    def test_timestamp_headers_survive_fragmented_header_and_jpeg_reads(self):
        parser = JpegParser()
        self.assertIsNone(parser.feed(b'--frame\r\nX-Camera-Captured-Mono'))
        self.assertIsNone(parser.feed(b'tonic: 123.125\r\n\r\n\xff\xd8first'))
        self.assertEqual(parser.feed(b'\xff\xd9'),b'\xff\xd8first\xff\xd9')
        self.assertEqual(parser.source_timestamp,123.125)
        parser.feed(b'--frame\r\nX-Camera-Captured-Monotonic: 124\r\n\r\n\xff\xd8second\xff\xd9')
        self.assertEqual(parser.source_timestamp,124)

    def test_latest_coalesced_frame_keeps_its_own_timestamp_and_legacy_is_supported(self):
        parser=JpegParser()
        for stamp in (100,101):
            data=f'X-Camera-Captured-Monotonic: {stamp}\r\n\r\n'.encode()+b'\xff\xd8data\xff\xd9'
            if stamp==100: first=data
        self.assertEqual(parser.feed(first+data),b'\xff\xd8data\xff\xd9')
        self.assertEqual(parser.source_timestamp,101)
        parser.feed(b'\xff\xd8legacy\xff\xd9')
        self.assertIsNone(parser.source_timestamp)

    def test_arbitrary_header_noise_is_bounded_and_bad_timestamp_is_rejected(self):
        parser=JpegParser(); parser.feed(b'x' * 20000)
        self.assertLessEqual(len(parser.buffer),4096)
        with self.assertRaises(ValueError):
            parser.feed(b'X-Camera-Captured-Monotonic: nan\r\n\r\n\xff\xd8x\xff\xd9')

    def test_queue_growth_is_detected_even_when_old_frames_keep_arriving(self):
        delay=StreamDelay()
        self.assertEqual(delay.observe(100,1000),0)
        self.assertAlmostEqual(delay.observe(100.1,1000.5),.4)
        with self.assertRaises(ValueError): delay.observe(100.2,1001.4)
        # Reconnect creates a new baseline; clocks need not share an epoch.
        self.assertEqual(StreamDelay().observe(120,1020),0)

    def test_source_reset_requires_new_stream_and_legacy_does_not_invent_latency(self):
        delay=StreamDelay(); delay.observe(100,1000)
        with self.assertRaises(ValueError): delay.observe(10,1001)
        self.assertEqual(StreamDelay().observe(None,1000),0)

    def test_receiver_closes_stale_stream_and_clears_instead_of_publishing_delayed_frame(self):
        now=[1000.0]; stopped=[False]; index=[0]
        def read(_):
            index[0]+=1
            source=100 if index[0]==1 else 100.1
            now[0]=1000 if index[0]==1 else 1001.5
            return f'X-Camera-Captured-Monotonic: {source}\r\n\r\n'.encode()+b'\xff\xd8frame\xff\xd9'
        response=SimpleNamespace(status=200,read1=read)
        conn=SimpleNamespace(request=Mock(),getresponse=lambda:response,close=Mock())
        stop=SimpleNamespace(is_set=lambda:stopped[0],wait=lambda _:stopped.__setitem__(0,True))
        slot=LatestFrame(lambda:now[0]); slot.publish=Mock(wraps=slot.publish)
        with patch('camera_frame_relay.http.client.HTTPConnection',return_value=conn), patch('camera_frame_relay.time.monotonic',side_effect=lambda:now[0]):
            receive_frames(slot,stop)
        self.assertEqual(slot.publish.call_count,1)
        self.assertIsNone(slot.read()[0])
        self.assertEqual(slot.reconnects,1)
        conn.close.assert_called_once()

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
