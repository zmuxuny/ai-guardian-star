import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from src.personalization_v5 import Store
from test_personalization_v5 import NOW, reminder
from tools.personalization_v5_text import Server, flush_outbox, post, prepared_session


class Client:
    def __init__(self):
        self.calls = []
        self.fail = False

    def classify(self, text, *, timeout=5):
        self.calls.append(text)
        if self.fail:
            raise ConnectionError('synthetic outage')
        return {'intent': 'needs_help'}


class FastV5Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.model = Store(root/'model.sqlite', 'test-device', 'model', clock=lambda: NOW+1)
        self.peer = Store(root/'peer.sqlite', 'test-device', 'peer', clock=lambda: NOW+1)
        self.client = Client()

    def setup_service(self):
        self.session, self.gate = prepared_session(self.model, self.client, policy='v4-fast')
        self.server = Server(self.model, self.session, readiness=self.gate)
        self.receiver = Server(self.peer)
        for server in (self.server, self.receiver):
            server.start()
            self.addCleanup(server.close)

    def accept(self):
        self.peer.register_reminder(reminder())
        flush_outbox(self.peer, self.server.url)
        self.assertEqual(self.session.tick('e1', prompt_available=self.gate.ready)['kind'], 'prompt')
        self.session.displayed('e1')

    def answer(self, text):
        return post(self.server.url+'/text/v1/answers', {'event_id': 'e1', 'text': text}, timeout=7)

    def test_default_preserves_v3_and_invalid_policy_is_rejected(self):
        default, _ = prepared_session(self.model, self.client)
        out = default.classify('我没有说我需要帮助。', timeout=5)
        self.assertEqual(out['policy_version'], 'experimental-care-text/3')
        self.assertEqual(out['intent'], 'needs_help')
        with self.assertRaises(ValueError):
            prepared_session(self.model, self.client, policy='unknown')

    def test_cold_gate_and_two_denials_use_no_classification_and_return_unclear(self):
        self.setup_service()
        url = self.server.url+'/personalization/v2/reminders'
        self.assertEqual(post(url, reminder())[0], 503)
        self.assertEqual(self.model.events(), [])
        self.assertTrue(self.gate.warm())
        prepared_calls = len(self.client.calls)
        self.accept()
        self.assertEqual(self.answer('我没有说我需要帮助。')[0], 202)
        self.assertEqual(self.session.tick('e1')['attempt'], 2)
        self.session.displayed('e1')
        code, value = self.answer('我未曾要求家人过来搭把手。')
        self.assertEqual((code, value['response']), (200, 'unclear'))
        self.assertEqual(len(self.client.calls), prepared_calls)
        self.assertEqual(self.gate.snapshot()['classification_calls'], 0)
        flush_outbox(self.model, self.receiver.url)
        self.assertEqual(self.peer.event('e1')['latest'], value)
        self.assertEqual(self.peer.help_tasks(), [])

    def test_existing_help_after_denial_survives_closed_gate_and_duplicate_delivery(self):
        self.setup_service()
        self.assertTrue(self.gate.warm())
        self.accept()
        self.assertEqual(self.answer('我没有说我需要帮助。')[0], 202)
        self.gate.invalidate('synthetic restart')
        self.assertEqual(post(self.server.url+'/personalization/v2/reminders', reminder('new'))[0], 503)
        self.assertEqual(post(self.server.url+'/personalization/v2/reminders', reminder())[1]['disposition'], 'duplicate')
        code, value = self.answer('我没说我需要帮助，但我现在起不来。')
        self.assertEqual((code, value['response']), (200, 'needs_help'))
        flush_outbox(self.model, self.receiver.url)
        self.assertEqual(post(self.receiver.url+'/personalization/v2/results', value)[1]['disposition'], 'duplicate')
        self.assertEqual(len(self.peer.help_tasks()), 1)
        self.assertEqual(self.gate.snapshot()['classification_calls'], 0)

    def test_model_failure_revokes_gate_then_same_session_recovers(self):
        self.setup_service()
        self.assertTrue(self.gate.warm())
        self.accept()
        self.client.fail = True
        self.assertEqual(self.answer('我没有表示不舒服，但我想找人来看看我。')[0], 202)
        self.assertFalse(self.gate.ready)
        self.client.fail = False
        self.assertTrue(self.gate.warm())
        code, value = self.answer('我没有表示不舒服，但我想找人来看看我。')
        self.assertEqual((code, value['response']), (200, 'needs_help'))
        self.assertEqual(self.gate.snapshot()['classification_calls'], 2)
        flush_outbox(self.model, self.receiver.url)
        self.assertTrue(self.peer.event('e1')['help_required'])

    def test_cli_lists_candidate_and_rejects_unknown_before_creating_database(self):
        command = [sys.executable, '-m', 'tools.personalization_v5_text', 'serve']
        help_result = subprocess.run(command+['--help'], capture_output=True, text=True)
        self.assertEqual(help_result.returncode, 0)
        self.assertIn('--policy', help_result.stdout)
        self.assertIn('v4-fast', help_result.stdout)
        path = Path(self.tmp.name)/'uncreated.sqlite'
        invalid = subprocess.run(command+['--role', 'model', '--db', str(path), '--device', 'test-device',
                                         '--port', '0', '--policy', 'unknown'], capture_output=True)
        self.assertEqual(invalid.returncode, 2)
        self.assertFalse(path.exists())
