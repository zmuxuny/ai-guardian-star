import json
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import http.client
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

from src.personalization_v5 import Store
from src.personalization_v5_session import Session
from tools.personalization_v5_text import Server, flush_outbox, post
from test_personalization_v5 import NOW, reminder, result


class HTTPTests(unittest.TestCase):
    def test_shared_service_factory_revokes_gate_on_transport_failure_but_accepts_rule_help(self):
        from test_local_care_prototype import Handler
        from tools.personalization_v5_text import prepared_session
        from tools.local_care_text_v3 import SemanticIntentClient
        Handler.mode='valid'
        backend=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=backend.serve_forever,daemon=True);worker.start()
        client=SemanticIntentClient('http://127.0.0.1:'+str(backend.server_port),'standin')
        session,gate=prepared_session(self.model,client)
        self.model_server.close()
        server=Server(self.model,session,readiness=gate);server.start();self.addCleanup(server.close)
        try:
            self.assertEqual(post(server.url+'/personalization/v2/reminders',reminder())[0],503)
            self.assertTrue(gate.warm())
            self.assertEqual(post(server.url+'/personalization/v2/reminders',reminder())[0],200)
            session.tick('e1');session.displayed('e1')
            backend.shutdown();backend.server_close();worker.join()
            self.assertEqual(post(server.url+'/text/v1/answers',{'event_id':'e1','text':'我想找人来看看我。'},timeout=7)[0],202)
            self.assertFalse(gate.ready)
            self.assertEqual(post(server.url+'/personalization/v2/reminders',reminder('new'))[0],503)
            code,out=post(server.url+'/text/v1/answers',{'event_id':'e1','text':'我现在起不来，帮帮我。'},timeout=7)
            self.assertEqual(code,200);self.assertEqual(out['response'],'needs_help')
        finally:
            if worker.is_alive():backend.shutdown();backend.server_close();worker.join()

    def test_readiness_blocks_new_reminders_without_reserving_slot_but_preserves_duplicates(self):
        from src.local_model_readiness import ModelReadiness
        gate=ModelReadiness(lambda text,timeout:{'intent':'okay'})
        self.model_server.readiness=gate
        url=self.model_server.url+'/personalization/v2/reminders'
        self.assertEqual(post(url,reminder())[0],503)
        self.assertEqual(self.model.events(),[])
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(self.model_server.url+'/health/ready',timeout=3)
        self.assertEqual(caught.exception.code,503);caught.exception.close()
        self.assertTrue(gate.warm())
        self.assertEqual(post(url,reminder())[1]['disposition'],'accepted')
        gate.invalidate()
        self.assertEqual(post(url,reminder())[1]['disposition'],'duplicate')
        self.assertEqual(post(url,reminder('new'))[0],503)

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
        for body in (b'[]',b'{"schema_version":"2","schema_version":"3"}',b'{bad'):
            req=urllib.request.Request(url,data=body,headers={'Content-Type':'application/json'})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req,timeout=3)
            self.assertIn(caught.exception.code,(400,413))
            caught.exception.close()
        conn=http.client.HTTPConnection('127.0.0.1',self.model_server.http.server_port,timeout=3)
        try:
            conn.request('POST','/personalization/v2/reminders',headers={'Content-Type':'application/json','Content-Length':'65537'})
            response=conn.getresponse();self.assertEqual(response.status,413);response.read()
        finally:conn.close()

    def test_deeply_nested_ack_retries_instead_of_killing_delivery_worker(self):
        class BadAck(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                body=b'['*30000+b'0'+b']'*30000
                self.send_response(200);self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
        server=ThreadingHTTPServer(('127.0.0.1',0),BadAck)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            self.peer.register_reminder(reminder())
            flush_outbox(self.peer,'http://127.0.0.1:'+str(server.server_port))
            self.assertEqual(self.peer.pending(),[])
            self.now+=5
            self.assertEqual(self.peer.pending()[0]['attempts'],1)
        finally:server.shutdown();server.server_close();worker.join()

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

    def test_http_model_adapter_reads_real_sse_transport_with_a_standin_backend(self):
        from test_local_care_prototype import Handler
        from tools.personalization_v5_text import run_demo
        Handler.mode='valid'
        backend=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=backend.serve_forever,daemon=True);worker.start()
        try:
            output=run_demo(Path(self.tmp.name)/'sse-demo',model_url='http://127.0.0.1:'+str(backend.server_port))
            self.assertEqual(output['mode'],'text_with_HTTP_model_backend')
            self.assertEqual(output['backend_attempts'],2)
            decisions=output['cases'][2]['policy_decisions']
            self.assertTrue(all(x['source']=='model_advisory' and x['model_intent']=='unclear' for x in decisions))
        finally:backend.shutdown();backend.server_close();worker.join()


if __name__=='__main__':unittest.main()
