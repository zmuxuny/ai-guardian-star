import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import board_face_bridge as bridge


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status = status
        self._raw = json.dumps(payload).encode('utf-8')

    def read(self, _limit):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class BoardFaceBridgeTests(unittest.TestCase):
    def test_requires_loopback_url_and_server_side_token(self):
        cases = (
            {'BOARD_FACE_BASE_URL': 'http://evil.example:6001', 'BOARD_FACE_ADMIN_TOKEN': 'secret'},
            {'BOARD_FACE_BASE_URL': 'http://127.0.0.1:6001', 'BOARD_FACE_ADMIN_TOKEN': ''},
            {'BOARD_FACE_BASE_URL': 'https://127.0.0.1:6001', 'BOARD_FACE_ADMIN_TOKEN': 'secret'},
        )
        for environment in cases:
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=False):
                with self.assertRaises(bridge.BoardFaceUnavailable):
                    bridge.enroll('Yang', 'test', b'image', 'image/jpeg')

    def test_forwards_bounded_contract_and_admin_token(self):
        captured = {}

        def open_request(request, timeout):
            captured['request'] = request
            captured['timeout'] = timeout
            return FakeResponse({'ok': True, 'recognition_status': 'ready', 'photo_count': 2})

        environment = {'BOARD_FACE_BASE_URL': 'http://127.0.0.1:6001',
                       'BOARD_FACE_ADMIN_TOKEN': 'server-only-secret'}
        with patch.dict(os.environ, environment), patch.object(bridge._OPENER, 'open', side_effect=open_request):
            result = bridge.enroll('老人', 'test', b'jpeg-data', 'image/jpeg')

        request = captured['request']
        self.assertEqual(request.full_url, 'http://127.0.0.1:6001/api/face/enroll')
        self.assertEqual(request.get_header('X-admin-token'), 'server-only-secret')
        self.assertNotIn('server-only-secret'.encode(), request.data)
        self.assertIn(b'name="name"', request.data)
        self.assertIn('老人'.encode('utf-8'), request.data)
        self.assertIn(b'name="user_id"', request.data)
        self.assertIn(b'\r\n\r\ntest\r\n', request.data)
        self.assertIn(b'jpeg-data', request.data)
        self.assertEqual(captured['timeout'], 30)
        self.assertEqual(result['photo_count'], 2)


if __name__ == '__main__':
    unittest.main()
