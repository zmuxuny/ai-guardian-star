import contextlib
import json
from pathlib import Path
import sys
import tempfile
import os
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from care_control import Controller, create_control_router
from fastapi import FastAPI
from fastapi.testclient import TestClient

SECRET = 'test-only-operator-secret-with-32-characters'
ORIGIN = {'Origin': 'http://testserver'}


class AuthTests(unittest.TestCase):
    def client(self, controller=None):
        self.controller = controller or SimpleNamespace(status=lambda: {'status':'idle'},
                                                       request=lambda enabled: {'status':'pending','enabled':enabled})
        app = FastAPI()
        app.include_router(create_control_router(lambda:'off', self.controller, lambda:SECRET))
        return TestClient(app)

    def test_requires_password_and_same_origin_and_rejects_extra_fields(self):
        c=self.client()
        self.assertEqual(401,c.put('/api/care-control/mode',json={'enabled':True},headers=ORIGIN).status_code)
        self.assertEqual(401,c.post('/api/care-control/unlock',json={'password':'wrong'},headers=ORIGIN).status_code)
        self.assertEqual(403,c.post('/api/care-control/unlock',json={'password':SECRET},headers={'Origin':'https://attacker.invalid'}).status_code)
        self.assertEqual(200,c.post('/api/care-control/unlock',json={'password':SECRET},headers=ORIGIN).status_code)
        self.assertEqual(422,c.put('/api/care-control/mode',json={'enabled':'yes'},headers=ORIGIN).status_code)
        self.assertEqual(422,c.put('/api/care-control/mode',json={'enabled':True,'command':'id'},headers=ORIGIN).status_code)
        self.assertEqual(202,c.put('/api/care-control/mode',json={'enabled':True},headers=ORIGIN).status_code)

    def test_signed_unlock_survives_server_restart_and_lock_clears_it(self):
        c=self.client();r=c.post('/api/care-control/unlock',json={'password':SECRET},headers=ORIGIN)
        self.assertIn('HttpOnly',r.headers['set-cookie']);self.assertIn('SameSite=strict',r.headers['set-cookie'])
        cookies=c.cookies
        c=self.client();c.cookies.update(cookies)
        self.assertEqual('off',c.get('/api/care-control/status').json()['mode'])
        self.assertEqual(200,c.post('/api/care-control/lock',headers=ORIGIN).status_code)
        self.assertEqual(401,c.get('/api/care-control/status').status_code)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.commands=[]
        self.c=Controller(self.root, self.root/'kit', self.root/'app',
                          runner=lambda args,**kw:self.commands.append(args),
                          guard=lambda:contextlib.nullcontext())

    def test_queue_is_durable_and_deduplicated_and_has_no_shell(self):
        self.c.request(True)
        state=json.loads((self.root/'state.json').read_text())
        self.assertEqual('pending',state['status'])
        self.assertTrue(state['enabled'])
        self.assertTrue(any('systemd-run' in x for x in self.commands[0]))
        self.assertFalse(any('sh'==x or 'bash'==x for x in self.commands[0]))
        with self.assertRaises(ValueError):self.c.request(False)
        self.assertNotIn(str(self.root),str(self.c.status()))

    def test_worker_starts_audio_demo_and_recovers_owned_session(self):
        calls=[]
        class Device:
            def __init__(self,session,app):self.session=Path(session);self.mode='off'
            def probe(self):return dict(status='PASS',care_mode=self.mode,care_config_present=self.mode!='off')
            def start_shadow(self,**kw):calls.append(('start',kw));self._arm_watchdog();self.mode='shadow'
            def recover_off(self):calls.append(('off',str(self.session)));self.mode='off'
        self.c.arm_watchdog=lambda session:calls.append(('watchdog',str(session)))
        self.c.request(True);self.c.work(SimpleNamespace(DeviceRun=Device))
        self.assertEqual('done',self.c.status()['status'])
        self.assertEqual({'fast_demo':True,'audio_demo':True},calls[0][1])
        session=json.loads((self.root/'state.json').read_text())['session']
        self.c.request(False);self.c.work(SimpleNamespace(DeviceRun=Device))
        self.assertEqual(('off',session),calls[-1])
        self.assertEqual('done',self.c.status()['status'])

    def test_failed_launch_is_not_reported_as_success(self):
        def fail(*a,**kw):raise OSError('private command details')
        self.c.runner=fail
        with self.assertRaises(OSError):self.c.request(True)
        self.assertEqual('error',self.c.status()['status'])
        self.assertNotIn('private command details',str(self.c.status()))

    def test_probe_connection_error_retries_before_rollback(self):
        calls=[]
        class Device:
            def __init__(self,session,app):self.session=session;self.probes=0
            def start_shadow(self,**kw):calls.append('start')
            def recover_off(self):calls.append('off')
            def probe(self):
                self.probes+=1
                if self.probes==1:raise ConnectionResetError()
                return dict(status='PASS',care_mode='shadow',care_config_present=True)
        self.c.request(True)
        with patch('care_control.time.sleep'):
            self.c.work(SimpleNamespace(DeviceRun=Device))
        self.assertEqual('done',self.c.status()['status']);self.assertEqual(['start'],calls)

    def test_continuous_probe_failure_eventually_recovers(self):
        calls=[]
        class Device:
            def __init__(self,session,app):self.session=session
            def start_shadow(self,**kw):pass
            def probe(self):calls.append('probe');raise ConnectionResetError()
            def recover_off(self):calls.append('off')
        self.c.request(True)
        with patch('care_control.time.sleep'), self.assertRaises(ValueError):
            self.c.work(SimpleNamespace(DeviceRun=Device))
        self.assertEqual(20,calls.count('probe'));self.assertEqual('off',calls[-1])
        self.assertEqual('error',self.c.status()['status'])

    @unittest.skipUnless(os.name=='posix','Linux flock integration')
    def test_worker_waits_for_request_to_release_operation_lock(self):
        controller=Controller(self.root)
        acquired=threading.Event()
        def worker():
            with controller.worker_guard():acquired.set()
        with controller.guard():
            thread=threading.Thread(target=worker);thread.start()
            self.assertFalse(acquired.wait(.1))
        thread.join(2)
        self.assertTrue(acquired.is_set())


if __name__=='__main__':unittest.main()
