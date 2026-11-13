import importlib.util
import io
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class JsonResponse(dict):
    def __init__(self, value):
        super().__init__(value)
        self.headers = {}


class FakeApp:
    def __init__(self):
        self.routes = {}

    def post(self, path):
        def decorator(function):
            self.routes[path] = function
            return function
        return decorator


class FaceCloudApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fake_g = types.SimpleNamespace(current_username='test')
        cls.fake_request = types.SimpleNamespace(content_length=100, form={}, files={})
        fake_flask = types.ModuleType('flask')
        fake_flask.g = cls.fake_g
        fake_flask.request = cls.fake_request
        fake_flask.jsonify = lambda **kwargs: JsonResponse(kwargs)
        spec = importlib.util.spec_from_file_location('face_api_under_test', ROOT / 'face_api.py')
        cls.api = importlib.util.module_from_spec(spec)
        old_flask = sys.modules.get('flask')
        sys.modules['flask'] = fake_flask
        try:
            spec.loader.exec_module(cls.api)
        finally:
            if old_flask is None:
                del sys.modules['flask']
            else:
                sys.modules['flask'] = old_flask

    def setUp(self):
        self.app = FakeApp()
        self.api.register_face_routes(self.app, lambda function: function)
        self.route = self.app.routes['/api/face/enroll']
        self.fake_g.current_username = 'test'
        self.fake_request.content_length = 100
        self.fake_request.form = {'name': '老人'}
        self.fake_request.files = {
            'file': types.SimpleNamespace(mimetype='image/jpeg', stream=io.BytesIO(b'jpeg-data'))
        }
        self.api.allowed_users = lambda _path: {'test'}

    def test_binds_board_user_id_to_authenticated_account(self):
        captured = {}

        def enroll(name, user_id, image, mime):
            captured.update(name=name, user_id=user_id, image=image, mime=mime)
            return {'ok': True, 'recognition_status': 'ready', 'photo_count': 1, 'hint': 'hint'}

        self.api.board_bridge.enroll = enroll
        result = self.route()
        self.assertTrue(result['success'])
        self.assertEqual(result['photoCount'], 1)
        self.assertEqual(captured, {'name': '老人', 'user_id': 'test',
                                    'image': b'jpeg-data', 'mime': 'image/jpeg'})
        self.assertEqual(result.headers['Cache-Control'], 'no-store')

    def test_denies_account_outside_device_allowlist(self):
        self.api.allowed_users = lambda _path: set()
        response, status = self.route()
        self.assertEqual(status, 403)
        self.assertFalse(response['success'])

    def test_unsafe_or_long_account_is_stably_mapped(self):
        first = self.api.account_face_id('person@example.com')
        second = self.api.account_face_id('person@example.com')
        self.assertEqual(first, second)
        self.assertRegex(first, r'^acct_[0-9a-f]{32}$')
        self.assertEqual(self.api.account_face_id('safe_user-1'), 'safe_user-1')

    def test_rejects_oversize_before_forwarding(self):
        self.fake_request.content_length = self.api.MAX_MULTIPART_BYTES + 1
        response, status = self.route()
        self.assertEqual(status, 413)
        self.assertIn('8 MiB', response['message'])


if __name__ == '__main__':
    unittest.main()
