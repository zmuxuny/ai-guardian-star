"""Capture timestamp/bytes association and real MJPEG generator, without camera/ACL."""
import asyncio
import threading
from types import SimpleNamespace
import unittest

from test_runtime import load_definition


class TimestampTests(unittest.TestCase):
    def test_encode_failure_or_throttle_does_not_relabel_the_last_jpeg(self):
        clock=[100.0]; succeeds=[True]
        cv=SimpleNamespace(IMWRITE_JPEG_QUALITY=1,
            imencode=lambda *a:(succeeds[0],SimpleNamespace(tobytes=lambda:b'jpeg')))
        ns=dict(time=SimpleNamespace(time=lambda:clock[0],monotonic=lambda:clock[0]),
            cv2=cv,JPEG_SIZE=(640,480),JPEG_QUALITY=50,MAX_ENCODE_FPS=20,
            lock=threading.Lock(),encoded_frame_bytes=None,encoded_frame_monotonic=0.0,last_encode_time=0.0)
        update=load_definition('ascend_video_stream.py','update_frame',ns)
        packet=load_definition('ascend_video_stream.py','get_current_frame_packet',ns)
        image=SimpleNamespace(shape=(480,640,3))
        update(image,captured_at=42)
        self.assertEqual(packet(),(b'jpeg',42))
        clock[0]=100.01; update(image,captured_at=43)
        self.assertEqual(packet(),(b'jpeg',42))
        clock[0]=101; succeeds[0]=False; update(image,captured_at=44)
        self.assertEqual(packet(),(b'jpeg',42))
        clock[0]=102; succeeds[0]=True; update(image)
        self.assertEqual(packet(),(b'jpeg',102))


class MjpegTimestampTests(unittest.IsolatedAsyncioTestCase):
    async def test_actual_generator_carries_the_timestamp_of_the_same_jpeg(self):
        ns=dict(video_hw=SimpleNamespace(get_current_frame_packet=lambda:(b'jpeg',123.25)),
            camera_video_is_live=lambda:True,asyncio=asyncio,
            StreamingResponse=lambda body,**kwargs:SimpleNamespace(body=body))
        generate=load_definition('ascend_board_server.py','video_feed',ns)
        response=await generate()
        part=await anext(response.body)
        self.assertIn(b'X-Camera-Captured-Monotonic: 123.250000\r\n\r\njpeg',part)
        await response.body.aclose()
