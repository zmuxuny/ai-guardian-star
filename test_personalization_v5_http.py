import json
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.personalization_v5 import Store
from src.personalization_v5_session import Session
from tools.personalization_v5_text import Server, flush_outbox, post
from test_personalization_v5 import NOW, reminder, result


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.now=NOW+1
        self.model=Store(Path(self.tmp.name)/'model.sqlite','test-device','model',clock=lambda:self.now)
        self.peer=Store(Path(self.tmp.name)/'peer.sqlite','test-device','peer',clock=lambda:self.now)
        self.classify=lambda text,timeout:{'intent':'needs_help' if text=='帮忙' else 'okay'}
        self.session=Session(self.model,self.classify)
        self.model_server=Server(self.model,self.session);self.model_server.start();self.addCleanup(self.model_server.close)
        self.peer_server=Server(self.peer);self.peer_server.start();self.addCleanup(self.peer_server.close)

    def test_real_http_text_closed_loop_and_duplicate_help(self):
        self.peer.register_reminder(reminder())
        flush_outbox(self.peer,self.model_server.url)
        self.assertEqual(self.peer.pending(),[])
        self.assertEqual(self.session.tick('e1')['kind'],'prompt');self.session.displayed('e1')
        code,body=post(self.model_server.url+'/text/v1/answers',{'event_id':'e1','text':'帮忙'},timeout=7)
        self.assertEqual(code,200);self.assertEqual(body['response'],'needs_help')
        flush_outbox(self.model,self.peer_server.url)
        self.assertTrue(self.peer.event('e1')['help_required'])
        self.assertEqual(post(self.peer_server.url+'/personalization/v2/results',body)[1]['disposition'],'duplicate')
        self.assertEqual(len(self.peer.help_tasks()),1)

    def test_busy_duplicate_unknown_version_and_unregistered_result(self):
        url=self.model_server.url+'/personalization/v2/reminders'
        self.assertEqual(post(url,reminder())[0],200)
        self.assertEqual(post(url,reminder('busy'))[0],503)
        self.assertEqual(post(url,reminder())[1]['disposition'],'duplicate')
        self.assertEqual(post(url,{**reminder(),'schema_version':'3'})[0],422)
        self.assertEqual(post(self.peer_server.url+'/personalization/v2/results',result())[0],404)

    def test_disconnect_retry_survives_store_reopen_without_changing_payload(self):
        self.peer.register_reminder(reminder())
        flush_outbox(self.peer,'http://127.0.0.1:1')
        self.assertEqual(self.peer.pending(),[])
        self.now+=5
        reopened=Store(self.peer.path,'test-device','peer',clock=lambda:self.now)
        self.assertEqual(reopened.pending()[0]['payload']['timestamp'],reminder()['timestamp'])
        flush_outbox(reopened,self.model_server.url)
        self.assertEqual(reopened.pending(),[])

    def test_invalid_json_duplicate_keys_and_oversized_body_are_rejected(self):
        url=self.model_server.url+'/personalization/v2/reminders'
        for body in (b'[]',b'{"schema_version":"2","schema_version":"3"}',b'{bad',b'x'*65537):
            req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req,timeout=3)
            self.assertIn(caught.exception.code,(400,413))
            caught.exception.close()

    def test_lost_ack_can_arrive_after_result_without_reverting_progress(self):
        self.peer.register_reminder(reminder())
        pending=self.peer.pending()[0]
        accepted=post(self.model_server.url+'/personalization/v2/reminders',pending['payload'])[1]
        self.peer.record_delivery(pending['id'],0,None)
        self.session.tick('e1');self.session.displayed('e1')
        output=self.session.answer('e1','好')
        flush_outbox(self.model,self.peer_server.url)
        self.peer.record_delivery(pending['id'],200,accepted)
        self.assertEqual(self.peer.event('e1')['latest'],output)
        self.assertEqual(self.peer.pending(),[])

    def test_non_loopback_targets_and_second_runner_are_refused(self):
        self.assertRaises(ValueError,Server,self.model,self.session,host='0.0.0.0')
        self.assertRaises(ValueError,post,'https://example.com/personalization/v2/results',result())
        self.assertRaises(RuntimeError,Server,self.model,self.session)

    def test_single_command_demo_reports_mode_and_actual_policy_sources(self):
        from tools.personalization_v5_text import run_demo
        output=run_demo(Path(self.tmp.name)/'demo')
        self.assertTrue(output['synthetic'])
        self.assertEqual(output['mode'],'text_rules_with_stub')
        self.assertEqual([x['result']['response'] for x in output['cases']],['ok','needs_help','unclear'])
        self.assertEqual(output['help_tasks'],1)
        self.assertGreater(output['backend_attempts'],0)
        self.assertRaises(FileExistsError,run_demo,Path(self.tmp.name)/'demo')


if __name__=='__main__':unittest.main()
