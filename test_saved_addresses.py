"""Saved-residence API checks against an isolated SQLite DB and Flask client.

Existing bearer/session verification is outside this module; the test decorator
only supplies two synthetic account identities to exercise ownership boundaries.
"""
import functools
import sqlite3
import tempfile
import unittest
from pathlib import Path
from flask import Flask, g, request, jsonify
from address_service import create_address_schema, register_address_routes


class SavedAddressTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'addresses.sqlite'
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE t_user(username TEXT PRIMARY KEY,address TEXT)')
            db.executemany('INSERT INTO t_user VALUES(?,?)', [('alice', ''), ('bob', '')])
        db.close()
        self.app = Flask(__name__)
        self.app.config['TESTING'] = True

        def require_auth(function):
            @functools.wraps(function)
            def wrapper(*args, **kwargs):
                header = request.headers.get('Authorization', '')
                if header not in ('Bearer alice', 'Bearer bob'):
                    return jsonify(success=False), 401
                g.current_username = header[7:]
                return function(*args, **kwargs)
            return wrapper

        register_address_routes(self.app, require_auth, self.db)
        self.client = self.app.test_client()

    def db(self):
        db = sqlite3.connect(self.path)
        self.addCleanup(db.close)
        db.row_factory = sqlite3.Row
        create_address_schema(db)
        db.commit()
        return db

    def call(self, action='list', data=None, owner='alice'):
        return self.client.post('/api/addresses/' + action, json={} if data is None else data,
                                headers={'Authorization': 'Bearer ' + owner})

    def add(self, name='测试住处', **values):
        data = {'label': name, 'detail': '功能测试路1号，非真实住址', 'latitude': None, 'longitude': None}
        data.update(values)
        response = self.call('save', data)
        self.assertEqual(response.status_code, 200, response.get_json())
        return next(row for row in response.get_json()['addresses'] if row['label'] == name)

    @staticmethod
    def identity(row):
        return {'id': row['id'], 'version': row['version']}

    def test_auth_and_invalid_body(self):
        for action in ('list', 'save', 'default', 'delete'):
            self.assertEqual(self.client.post('/api/addresses/' + action, json={}).status_code, 401)
        self.assertEqual(self.call(data=['invalid']).status_code, 400)

    def test_create_edit_and_reload_persistence(self):
        row = self.add(latitude=30.0, longitude=104.0)
        self.assertTrue(row['isDefault'])
        draft = {**self.identity(row), 'label': '修改后的测试住处', 'detail': '功能测试路2号，非真实住址',
                 'latitude': -30.5, 'longitude': -104.25, 'isDefault': False}
        updated = self.call('save', draft).get_json()['addresses'][0]
        self.assertEqual(updated['detail'], draft['detail'])
        self.assertEqual(updated['latitude'], -30.5)
        self.assertTrue(updated['isDefault'])
        self.client = self.app.test_client()
        self.assertEqual(self.call().get_json()['addresses'][0], updated)

    def test_only_one_default_and_profile_stays_in_sync(self):
        first = self.add('测试一')
        second = self.add('测试二')
        result = self.call('default', self.identity(second)).get_json()
        self.assertEqual(sum(row['isDefault'] for row in result['addresses']), 1)
        self.assertEqual(result['addresses'][0]['id'], second['id'])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT address FROM t_user WHERE username=?', ('alice',)).fetchone()[0],
                             result['defaultAddress'])
        self.assertFalse(next(row for row in result['addresses'] if row['id'] == first['id'])['isDefault'])

    def test_delete_default_reassigns_and_last_delete_is_not_resurrected(self):
        first = self.add('测试一')
        self.add('测试二')
        result = self.call('delete', self.identity(first)).get_json()
        self.assertEqual(len(result['addresses']), 1)
        self.assertTrue(result['addresses'][0]['isDefault'])
        self.assertEqual(self.call('delete', self.identity(result['addresses'][0])).status_code, 200)
        self.assertEqual(self.call().get_json()['addresses'], [])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT address FROM t_user WHERE username=?', ('alice',)).fetchone()[0], '')

    def test_legacy_address_is_preserved_once(self):
        with self.db() as db:
            db.execute('UPDATE t_user SET address=? WHERE username=?', ('原有测试家庭地址', 'alice'))
        first = self.call().get_json()['addresses']
        self.assertEqual(len(first), 1)
        self.assertTrue(first[0]['isDefault'])
        self.assertEqual(first[0]['detail'], '原有测试家庭地址')
        self.assertEqual(self.call().get_json()['addresses'], first)

    def test_cross_account_ids_and_owner_spoofing_are_rejected(self):
        row = self.add()
        self.assertEqual(self.call(data={'username': 'alice'}, owner='bob').get_json()['addresses'], [])
        draft = {**self.identity(row), 'label': '其他人地址', 'detail': '不允许访问的测试地址'}
        for action, data in (('save', draft), ('default', self.identity(row)), ('delete', self.identity(row))):
            self.assertEqual(self.call(action, data, 'bob').status_code, 404)
        self.assertEqual(len(self.call().get_json()['addresses']), 1)

    def test_stale_version_does_not_overwrite_or_delete(self):
        row = self.add()
        self.call('save', {**self.identity(row), 'label': '新版测试住处', 'detail': '新版测试地址，非真实住址'})
        for action in ('default', 'delete'):
            self.assertEqual(self.call(action, self.identity(row)).status_code, 409)
        self.assertEqual(self.call().get_json()['addresses'][0]['label'], '新版测试住处')

    def test_coordinate_and_text_validation(self):
        invalid = [
            {'label': ''}, {'label': 'x' * 25}, {'detail': ''}, {'detail': 'x' * 301},
            {'latitude': 30}, {'longitude': 104}, {'latitude': 91, 'longitude': 0},
            {'latitude': 0, 'longitude': -181}, {'latitude': True, 'longitude': 0},
            {'latitude': float('nan'), 'longitude': 0}, {'latitude': 0, 'longitude': float('inf')},
            {'isDefault': 'true'}, {'label': 'invalid\x00'},
        ]
        for values in invalid:
            with self.subTest(values=values):
                body = {'label': '测试住处', 'detail': '功能测试地址，非真实住址', **values}
                self.assertEqual(self.call('save', body).status_code, 400)
        self.assertEqual(self.call().get_json()['addresses'], [])

    def test_zero_and_coordinate_boundaries_are_valid(self):
        self.assertEqual(self.add('零坐标', latitude=0, longitude=0)['latitude'], 0)
        self.assertEqual(self.add('边界坐标', latitude=-90, longitude=180)['longitude'], 180)

    def test_limit_is_account_scoped(self):
        for index in range(20):
            self.add(f'测试住处{index}')
        self.assertEqual(self.call('save', {'label': '第21处', 'detail': '超出数量限制的测试地址'}).status_code, 400)
        self.assertEqual(self.call('save', {'label': '另一个账号', 'detail': '另一账号的测试地址'}, 'bob').status_code, 200)

    def test_account_delete_trigger_removes_only_its_addresses(self):
        self.add()
        self.call('save', {'label': '另一个账号', 'detail': '另一账号的测试地址'}, 'bob')
        with self.db() as db:
            db.execute('DELETE FROM t_user WHERE username=?', ('alice',))
            self.assertEqual(db.execute('SELECT count(*) FROM t_saved_address WHERE username=?', ('alice',)).fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM t_saved_address WHERE username=?', ('bob',)).fetchone()[0], 1)

    def test_sensitive_results_are_not_http_cached(self):
        self.assertEqual(self.call().headers.get('Cache-Control'), 'no-store')

    def test_account_removed_after_auth_does_not_create_orphan_addresses(self):
        with self.db() as db:
            db.execute('DELETE FROM t_user WHERE username=?', ('alice',))
        response = self.call('save', {'label': '已删除的账号', 'detail': '不应保存的测试地址'})
        self.assertEqual(response.status_code, 401)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM t_saved_address').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
