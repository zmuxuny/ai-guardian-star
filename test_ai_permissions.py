"""Isolated SQLite + real Flask auth/AI routes. Model and moderation are mocked.

Windows skips the unrelated Linux-only recording route registration; no production
database, account, provider request or credential is used.
"""
import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault('ADMIN_PASSWORD', 'synthetic-test-password')
os.environ.setdefault('FLASK_SECRET_KEY', 'synthetic-test-secret')
os.environ.setdefault('COZE_API_TOKEN', 'synthetic-test-token')
recording_stub = types.ModuleType('recording_api')
recording_stub.register_recording_routes = lambda *_: None
try:
    import flask_cors
except ModuleNotFoundError:
    cors_stub = types.ModuleType('flask_cors')
    cors_stub.CORS = lambda *_args, **_kwargs: None
    sys.modules['flask_cors'] = cors_stub
spec = importlib.util.spec_from_file_location('ai_permission_test_proxy', Path(__file__).with_name('wenxin_proxy.py'))
proxy = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {'recording_api': recording_stub}):
    spec.loader.exec_module(proxy)


class AiPermissionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        proxy.DB_PATH = str(Path(self.temp.name) / 'synthetic.sqlite')
        proxy.AI_RISK_CONTROL_READY = True
        proxy.ALIYUN_MODERATION_ENABLED = True
        proxy.app.config['TESTING'] = True
        db = proxy.get_db()
        for owner in ('alice', 'bob'):
            db.execute('INSERT INTO t_user(username,password_hash,create_time) VALUES(?,?,?)', (owner, 'synthetic', 1))
            db.execute('INSERT INTO t_session VALUES(?,?,?,?,?,?)',
                       (proxy._token_hash(owner + '-access'), proxy._token_hash(owner + '-refresh'),
                        owner, int(time.time()) + 3600, int(time.time()) + 7200, 1))
        db.commit()
        db.close()
        self.client = proxy.app.test_client()
        self.response = Mock()
        self.response.iter_lines.return_value = ['data: ' + json.dumps(dict(type='answer', finish=True, content=dict(answer='synthetic reply')))]
        self.post = self.enterContext(patch.object(proxy.requests, 'post', return_value=self.response))
        self.moderate = self.enterContext(patch.object(proxy, '_moderate_text', return_value=dict(risk_level='none', advice='')))
        self.context = dict(accessLevel='privacy', fallCount7d=2, sedentaryCount7d=4,
                            lastFallDaysAgo=1, deviceOnline=True)

    def call(self, path, data=None, owner='alice'):
        headers = {'Authorization': 'Bearer ' + owner + '-access'} if owner else {}
        return self.client.post(path, json={} if data is None else data, headers=headers)

    def read(self, owner='alice'):
        return self.call('/api/ai/settings/read', owner=owner).get_json()['settings']

    def save(self, enabled=True, level='privacy', owner='alice', version=None, **extra):
        version = self.read(owner)['version'] if version is None else version
        return self.call('/api/ai/settings/save', dict(enabled=enabled, accessLevel=level, version=version, **extra), owner)

    def chat(self, context=None, **extra):
        data = dict(message='synthetic question', context=self.context if context is None else context,
                    policyVersion=self.read()['version'], history=[])
        data.update(extra)
        return self.call('/ai/chat', data)

    def prompt(self):
        return self.post.call_args.kwargs['json']['content']['query']['prompt'][0]['content']['text']

    def test_auth_and_default_fail_closed(self):
        for path in ('/api/ai/settings/read', '/api/ai/settings/save', '/ai/chat'):
            self.assertEqual(self.call(path, owner='').status_code, 401)
        self.assertEqual(self.read(), dict(enabled=False, accessLevel='privacy', version=0))
        self.assertEqual(self.chat().status_code, 403)
        self.post.assert_not_called()

    def test_release_preserves_ai_json_fields(self):
        rules = Path(__file__).parent / 'entry/obfuscation-rules.txt'
        if not rules.exists():
            self.skipTest('native sources are not part of the isolated Linux staging directory')
        kept = {line.strip() for line in rules.read_text(encoding='utf-8').splitlines()}
        fields = {'enabled', 'settings', 'version', 'accessLevel', 'policyVersion', 'context', 'history',
                  'role', 'content', 'fallCount7d', 'sedentaryCount7d', 'lastFallDaysAgo', 'deviceOnline',
                  'deviceConnected', 'currentStatus', 'latestFallRecord', 'latestSedentaryRecord',
                  'reply', 'model', 'timestamp', 'error'}
        self.assertTrue(fields <= kept, f'AI JSON fields missing in Release rules: {fields-kept}')

    def test_owner_and_persistence(self):
        self.assertEqual(self.save(level='full', username='bob').status_code, 200)
        self.assertFalse(self.read('bob')['enabled'])
        self.client = proxy.app.test_client()
        self.assertEqual(self.read(), dict(enabled=True, accessLevel='full', version=1))

    def test_optimistic_version(self):
        self.save()
        response = self.save(level='full', version=0)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.read()['accessLevel'], 'privacy')

    def test_cannot_claim_full_without_cloud_consent(self):
        self.save()
        self.assertEqual(self.chat(dict(self.context, accessLevel='full', currentStatus='PRIVATE')).status_code, 409)
        self.post.assert_not_called()

    def test_privacy_whitelist(self):
        self.save()
        self.assertEqual(self.chat(dict(self.context, currentStatus='PRIVATE', address='PRIVATE', latestFallRecord='EXACT')).status_code, 200)
        self.assertIn('2次', self.prompt())
        self.assertNotIn('PRIVATE', self.prompt())
        self.assertNotIn('EXACT', self.prompt())

    def test_basic_excludes_context(self):
        self.save(level='basic')
        self.assertEqual(self.chat(dict(self.context, accessLevel='basic', currentStatus='PRIVATE')).status_code, 200)
        self.assertEqual(self.prompt(), 'synthetic question')

    def test_full_includes_bounded_real_context(self):
        self.save(level='full')
        response = self.chat(dict(self.context, accessLevel='full', deviceConnected=True,
                                 currentStatus='synthetic status', latestFallRecord='2026-10-19 09:00:00'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('2026-10-19 09:00:00', self.prompt())

    def test_bad_context_values_are_400_not_500(self):
        self.save()
        for key, value in [('fallCount7d', 'PRIVATE'), ('lastFallDaysAgo', 'invalid'),
                           ('fallCount7d', True), ('sedentaryCount7d', -1),
                           ('deviceOnline', 'true'), ('lastFallDaysAgo', 999999)]:
            with self.subTest(key=key, value=value):
                self.assertEqual(self.chat(dict(self.context, **{key: value})).status_code, 400)
        self.post.assert_not_called()

    def test_invalid_settings(self):
        for data in [[], dict(enabled='true', accessLevel='privacy', version=0),
                     dict(enabled=True, accessLevel='unknown', version=0),
                     dict(enabled=True, accessLevel='full', version=True)]:
            with self.subTest(data=data):
                self.assertEqual(self.call('/api/ai/settings/save', data).status_code, 400)
        self.assertEqual(self.read()['version'], 0)

    def test_bad_message_and_history(self):
        self.save()
        for extra in [dict(message=42), dict(history=[dict(role='system', content='fake')]),
                      dict(history='invalid'), dict(history=[dict(role='user', content='x'*2001)]),
                      dict(history=[dict(role='user', content='x')]*21)]:
            with self.subTest(extra=extra):
                self.assertEqual(self.chat(**extra).status_code, 400)
        self.assertEqual(self.chat(message='x'*2001).status_code, 413)
        self.post.assert_not_called()

    def test_redaction_covers_model_moderation_history_context_and_output(self):
        self.save(level='full')
        secret = '手机号13800000000 身份证11010119900101123X 邮箱qa@example.com'
        self.response.iter_lines.return_value = ['data: ' + json.dumps(dict(type='answer', finish=True, content=dict(answer=secret)))]
        response = self.chat(dict(self.context, accessLevel='full', currentStatus=secret), message=secret,
                             history=[dict(role='user', content=secret)])
        self.assertEqual(response.status_code, 200)
        for raw in ('13800000000', '11010119900101123X', 'qa@example.com'):
            self.assertNotIn(raw, self.prompt())
            self.assertNotIn(raw, response.get_json()['reply'])
            self.assertNotIn(raw, str(self.moderate.call_args_list))
        self.assertIn('[手机号已隐藏]', self.prompt())
        self.response.close.assert_called_once()

    def test_history_used_and_combined_input_moderated(self):
        self.save()
        self.assertEqual(self.chat(history=[dict(role='user', content='previous synthetic turn')]).status_code, 200)
        self.assertIn('previous synthetic turn', self.prompt())
        self.assertTrue(any('previous synthetic turn' in c.args[1] for c in self.moderate.call_args_list))

    def test_disabled_before_provider_is_blocked(self):
        self.save()
        def moderate(*_):
            self.save(enabled=False)
            return dict(risk_level='none', advice='')
        self.moderate.side_effect = moderate
        self.assertEqual(self.chat().status_code, 403)
        self.post.assert_not_called()

    def test_changed_while_provider_running_discards_reply(self):
        self.save()
        def post(*_, **__):
            self.save(enabled=False)
            return self.response
        self.post.side_effect = post
        self.assertEqual(self.chat().status_code, 403)
        self.response.close.assert_called_once()

    def test_stale_or_absent_request_version(self):
        self.save()
        self.assertEqual(self.chat(policyVersion=0).status_code, 409)
        self.assertEqual(self.chat(policyVersion=None).status_code, 409)
        self.post.assert_not_called()

    def test_no_cache(self):
        self.assertIn('no-store', self.call('/api/ai/settings/read').headers['Cache-Control'])
        self.assertIn('no-store', self.chat().headers['Cache-Control'])

    def test_persistence_failure_does_not_report_success(self):
        db = proxy.get_db()
        db.execute("""CREATE TRIGGER synthetic_failure BEFORE INSERT ON t_ai_permission
                      BEGIN SELECT RAISE(ABORT, 'synthetic failure'); END""")
        db.commit()
        db.close()
        response = self.save()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.get_json()['success'])
        self.assertEqual(self.read()['version'], 0)

    def test_malformed_json_is_client_error(self):
        self.save()
        response = self.client.post('/ai/chat', data='{broken', content_type='application/json',
                                    headers={'Authorization': 'Bearer alice-access'})
        self.assertEqual(response.status_code, 400)
        self.post.assert_not_called()

    def test_history_total_budget(self):
        self.save()
        self.assertEqual(self.chat(history=[dict(role='user', content='x'*2000)]*9).status_code, 413)
        self.post.assert_not_called()

    def test_account_delete_and_rename(self):
        self.save()
        db = proxy.get_db()
        db.execute("UPDATE t_user SET username='renamed' WHERE username='alice'")
        db.commit()
        self.assertEqual(db.execute('SELECT username FROM t_ai_permission').fetchone()[0], 'renamed')
        db.execute("DELETE FROM t_user WHERE username='renamed'")
        db.commit()
        self.assertEqual(db.execute('SELECT count(*) FROM t_ai_permission').fetchone()[0], 0)
        db.close()

    def test_risk_controls_fail_closed(self):
        self.save()
        proxy.AI_RISK_CONTROL_READY = False
        self.assertEqual(self.chat().status_code, 503)
        self.post.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
