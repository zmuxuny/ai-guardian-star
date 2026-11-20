"""Operator-only care switch; worker survives the board service restart."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import threading
from collections import deque

COOKIE = 'guardian_care_operator'
PREFIX = '/api/care-control'
SESSION_SECONDS = 8 * 3600


class Controller:
    def __init__(self, root=None, kit=None, app=None, *, runner=None, guard=None):
        self.root = Path(root or os.environ.get('AI_GUARDIAN_CARE_WEB_ROOT', '/root/guardian-care-control'))
        self.kit = Path(kit or self.root/'kit')
        self.app = Path(app or '/root/ai_guardian')
        self.runner = runner or subprocess.check_output
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.guard = guard or self._guard
        self.worker_guard = guard or (lambda:self._guard(wait=True))

    @contextmanager
    def _guard(self, wait=False):
        import fcntl
        with (self.root/'operation.lock').open('a') as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
            except BlockingIOError:
                raise ValueError('operation_busy') from None
            try:
                yield
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def read(self):
        path = self.root/'state.json'
        return json.loads(path.read_text()) if path.exists() else {'status':'idle'}

    def save(self, state):
        path = self.root/('state.'+secrets.token_hex(8)+'.tmp')
        try:
            with path.open('x') as f:
                json.dump(state, f);f.flush();os.fsync(f.fileno())
            path.chmod(0o600);path.replace(self.root/'state.json')
        finally:
            if path.exists():path.unlink()

    def status(self):
        state = self.read()
        if state['status'] in ('pending','running') and state.get('expires',0)<time.time():
            state=dict(state,status='error',error='operation_timeout')
        return {key:state[key] for key in ('status','enabled','error','expires') if key in state}

    def request(self, enabled):
        if type(enabled) is not bool:raise ValueError('invalid_mode')
        with self.guard():
            state = self.read()
            if state['status'] in ('pending','running') and state.get('expires',0)>time.time():
                raise ValueError('operation_busy')
            state.update(status='pending', enabled=enabled, expires=time.time()+210, job=secrets.token_hex(12))
            state.pop('error',None);self.save(state)
            try:
                self.runner(['systemd-run','--quiet','--collect','--unit=guardian-care-web-'+state['job'],
                             '--property=Type=exec','--property=RuntimeMaxSec=180','--property=UMask=0077',
                             sys.executable,str(Path(__file__).resolve()),'worker','--root',str(self.root)],
                            stderr=subprocess.STDOUT,timeout=12)
            except Exception:
                state.update(status='error',error='launch_failed');self.save(state);raise
        return self.status()

    def arm_watchdog(self, session):
        unit = 'guardian-care-web-watchdog-'+secrets.token_hex(10)
        self.runner(['systemd-run','--quiet','--collect','--unit='+unit,'--property=Type=exec',
                     '--property=RuntimeMaxSec=1900','--property=UMask=0077',sys.executable,
                     str(self.kit/'tools/board_validation.py'),'watchdog','--session',str(session),
                     '--app-root',str(self.app)],stderr=subprocess.STDOUT,timeout=12)
        end=time.monotonic()+10
        while time.monotonic()<end:
            marker=Path(session)/'watchdog-armed.json'
            if marker.exists():
                pid=json.loads(marker.read_text())['pid']
                actual=self.runner(['systemctl','show',unit,'-p','MainPID','--value'],timeout=5)
                if int(actual)==pid and pid>0:return
            time.sleep(.1)
        raise ValueError('watchdog_not_confirmed')

    def work(self, validation):
        with self.worker_guard():
            state=self.read()
            if state['status']!='pending':raise ValueError('no_pending_operation')
            state['status']='running';self.save(state)
            device=None
            try:
                if state.get('session'):
                    session=Path(state['session'])
                    if session.parent!=self.root/'sessions':raise ValueError('invalid_owned_session')
                    device=validation.DeviceRun(session,self.app)
                if state['enabled']:
                    if device:device.recover_off()
                    session=self.root/'sessions'/secrets.token_hex(16)
                    state['session']=str(session);self.save(state)
                    device=validation.DeviceRun(session,self.app)
                    device._arm_watchdog=lambda:self.arm_watchdog(session)
                    device.start_shadow(fast_demo=True,audio_demo=True)
                elif device:
                    device.recover_off()
                else:
                    device=validation.DeviceRun(self.root/'checks',self.app)
                for attempt in range(20):
                    try:proof=device.probe()
                    except (OSError,ValueError,subprocess.SubprocessError):proof={}
                    expected='shadow' if state['enabled'] else 'off'
                    if proof.get('status')=='PASS' and proof.get('care_mode')==expected and bool(proof.get('care_config_present'))==state['enabled']:
                        state.update(status='done');self.save(state);return
                    if attempt<19:time.sleep(2)
                raise ValueError('mode_not_confirmed')
            except Exception:
                if state['enabled'] and device:
                    try:device.recover_off()
                    except Exception:pass
                state.update(status='error',error='switch_failed');self.save(state)
                raise


def create_control_router(mode_provider, controller=None, secret_provider=None):
    from fastapi import APIRouter, Body, HTTPException, Request, Response
    router=APIRouter(prefix=PREFIX)
    secret_provider=secret_provider or (lambda:os.environ.get('AI_GUARDIAN_CARE_WEB_TOKEN',''))
    holder=[controller];attempts=deque(maxlen=32);attempt_lock=threading.Lock()
    def secret():
        value=secret_provider()
        if len(value)<24:raise HTTPException(503,'control_not_configured')
        return value.encode()
    def origin(request):
        from urllib.parse import urlsplit
        parsed=urlsplit(request.headers.get('origin',''))
        if parsed.scheme not in ('http','https') or parsed.netloc!=request.headers.get('host'):
            raise HTTPException(403,'same_origin_required')
    def signature(expires):return hmac.new(secret(),str(expires).encode(),hashlib.sha256).hexdigest()
    def authenticate(request):
        secret()
        try:
            expiry,tag=request.cookies.get(COOKIE,'').split('.',1);expiry=int(expiry)
            if not time.time()<expiry<=time.time()+SESSION_SECONDS+60 or not hmac.compare_digest(tag,signature(expiry)):
                raise ValueError()
        except (ValueError,TypeError):raise HTTPException(401,'operator_unlock_required') from None
    def control():
        if holder[0] is None:holder[0]=Controller()
        return holder[0]
    @router.post('/unlock')
    def unlock(request:Request,response:Response,body:dict=Body(...)):
        origin(request);key=secret()
        with attempt_lock:
            now=time.monotonic()
            while attempts and now-attempts[0]>60:attempts.popleft()
            if len(attempts)>=20:raise HTTPException(429,'try_again_later')
            attempts.append(now)
        if set(body)!={'password'} or not isinstance(body['password'],str) or len(body['password'])>200:
            raise HTTPException(422,'invalid_unlock')
        if not hmac.compare_digest(hashlib.sha256(body['password'].encode()).digest(),hashlib.sha256(key).digest()):
            raise HTTPException(401,'incorrect_password')
        expiry=int(time.time())+SESSION_SECONDS
        response.set_cookie(COOKIE,str(expiry)+'.'+signature(expiry),max_age=SESSION_SECONDS,
                            httponly=True,samesite='strict',path=PREFIX,secure=request.url.scheme=='https')
        response.headers['Cache-Control']='no-store'
        return {'unlocked':True}
    @router.post('/lock')
    def lock(request:Request,response:Response):
        origin(request);authenticate(request)
        response.delete_cookie(COOKIE,path=PREFIX);return {'unlocked':False}
    @router.get('/status')
    def status(request:Request,response:Response):
        authenticate(request);response.headers['Cache-Control']='no-store'
        return dict(control().status(),mode=mode_provider(),unlocked=True)
    @router.put('/mode',status_code=202)
    def mode(request:Request,body:dict=Body(...)):
        origin(request);authenticate(request)
        if set(body)!={'enabled'} or type(body['enabled']) is not bool:raise HTTPException(422,'invalid_mode')
        try:return control().request(body['enabled'])
        except ValueError:raise HTTPException(409,'operation_busy') from None
        except (OSError,subprocess.SubprocessError):raise HTTPException(503,'control_launch_failed') from None
    return router


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['worker']);parser.add_argument('--root',required=True)
    args=parser.parse_args();controller=Controller(args.root)
    sys.path.insert(0,str(controller.kit))
    from tools import board_validation
    controller.work(board_validation)
