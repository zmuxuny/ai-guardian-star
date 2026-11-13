"""Cloud account API must stream board media only after user authorization."""
import io
import time
import unittest
from unittest.mock import patch

from flask import Flask, g

import recording_api


class BoardRecordingApiTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)

        def authenticated(function):
            def wrapper(*args, **kwargs):
                g.current_username = 'allowed'
                return function(*args, **kwargs)
            wrapper.__name__ = function.__name__
            return wrapper

        recording_api.register_recording_routes(self.app, authenticated)
        self.client = self.app.test_client()
        self.clip = {'id': 'abc123', 'segmentId': 'abc123', 'startTime': 1000,
                     'endTime': 2000, 'eventType': 'all', 'endUnconfirmed': False}
        self.as_of = int(time.time() * 1000)

    def test_query_and_media_use_authenticated_board_facade(self):
        result = {'success': True, 'asOf': self.as_of, 'windowStart': self.as_of - 86400000,
                  'windowEnd': self.as_of, 'status': 'recording', 'clips': [self.clip],
                  'eventCount': 0}
        with patch.object(recording_api, 'allowed_users', return_value={'allowed'}), \
                patch.object(recording_api.board_bridge, 'configured', return_value=True), \
                patch.object(recording_api.board_bridge, 'snapshot', return_value=result), \
                patch.object(recording_api.board_bridge, 'open_media', return_value=io.BytesIO(b'mp4-data')) as media:
            response = self.client.post('/api/recordings/query', json={'asOf': self.as_of, 'filter': 'all'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['clips'][0]['segmentId'], 'abc123')
            response = self.client.post('/api/recordings/media',
                                        json={'asOf': self.as_of, 'filter': 'all', 'clipId': 'abc123'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.data, b'mp4-data')
            media.assert_called_once_with('abc123')

    def test_account_allowlist_blocks_board_query(self):
        with patch.object(recording_api, 'allowed_users', return_value=set()), \
                patch.object(recording_api.board_bridge, 'configured', return_value=True), \
                patch.object(recording_api.board_bridge, 'snapshot') as snapshot:
            response = self.client.post('/api/recordings/query', json={'filter': 'all'})
            self.assertEqual(response.status_code, 403)
            snapshot.assert_not_called()


if __name__ == '__main__':
    unittest.main()
