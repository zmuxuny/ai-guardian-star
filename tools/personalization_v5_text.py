"""Loopback-only v5 text pilot. Run `python -m tools.personalization_v5_text -h`."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from src.personalization_v5 import ProtocolError, Store, string, iso
from src.personalization_v5_session import Session
from tools.local_care_text_v3 import SemanticIntentClient, classify_reply
from tools.local_llm_prep import endpoint, unique_object


def read_json(body):
    def invalid(value):
        raise ValueError('nonfinite JSON')
    try:
        return json.loads(body,object_pairs_hook=unique_object,parse_constant=invalid)
    except RecursionError as error:
        raise ValueError('JSON nesting exceeds parser limit') from error


def post(url, payload, *, timeout=3):
    parsed=urlsplit(url)
    origin='http://'+parsed.netloc
    host,port=endpoint(origin)
    if parsed.scheme!='http' or parsed.query or parsed.fragment or not parsed.path.startswith('/'):
        raise ValueError('explicit loopback HTTP URL required')
    body=json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
    if len(body)>65536:
        raise ValueError('payload exceeds 64 KiB')
    conn=http.client.HTTPConnection(host,port,timeout=timeout)
    sockets=[]
    def abort():
        for sock in sockets:
            try:sock.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        conn.close()
    deadline=time.monotonic()+timeout
    timer=threading.Timer(timeout,abort);timer.daemon=True;timer.start()
    try:
        conn.request('POST',parsed.path,body,{'Content-Type':'application/json'})
        if conn.sock is not None:sockets.append(conn.sock)
        response=conn.getresponse()
        raw=response.read(65537)
        if time.monotonic()>deadline:
            raise TimeoutError('HTTP deadline')
        if len(raw)>65536:
            raise ValueError('response exceeds 64 KiB')
        return response.status,read_json(raw.decode('utf-8'))
    finally:
        timer.cancel();conn.close()


def flush_outbox(store, target, *, stop=None):
    endpoint(target)
    route='/personalization/v2/reminders' if store.role=='peer' else '/personalization/v2/results'
    for item in store.pending():
        if stop is not None and stop.is_set():break
        if store.clock()>=item['deadline']:
            store.pending()
            continue
        try:
            code,ack=post(target.rstrip('/')+route,item['payload'],timeout=3)
        except (OSError,ValueError,http.client.HTTPException):
            code,ack=0,None
        store.record_delivery(item['id'],code,ack)


class Lease:
    """OS releases the exclusive runner lock on crash, never uses stale PID files."""
    def __init__(self,path):
        self.file=open(str(path)+'.runner.lock','a+b')
        try:
            if os.name=='nt':
                import msvcrt
                self.file.seek(0,2)
                if self.file.tell()==0:self.file.write(b'0');self.file.flush()
                self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise RuntimeError('another runner owns this database') from error

    def close(self):
        if self.file.closed:return
        if os.name=='nt':
            import msvcrt
            self.file.seek(0);msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
        self.file.close()


class Server:
    def __init__(self,store,session=None,*,host='127.0.0.1',port=0):
        if host!='127.0.0.1':raise ValueError('bind explicit IPv4 loopback only')
        if (store.role=='model') != (session is not None):raise ValueError('model requires session; peer must not have one')
        self.store,self.session=store,session
        self.input_healthy=True
        self._lease=Lease(store.path)
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def setup(self):
                super().setup();self.connection.settimeout(7)

            def reply(self,code,body):
                raw=json.dumps(body,ensure_ascii=False,allow_nan=False).encode('utf-8')
                self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

            def do_POST(self):
                try:
                    length=int(self.headers.get('Content-Length','-1'))
                    if not 0<=length<=65536:raise ProtocolError(413,'body exceeds limit or lacks length')
                    if self.headers.get('Transfer-Encoding') or self.headers.get('Content-Type','').split(';')[0]!='application/json':
                        raise ProtocolError(400,'Content-Type application/json required')
                    chunks=[];left=length;deadline=time.monotonic()+3
                    while left:
                        remaining=deadline-time.monotonic()
                        if remaining<=0:raise TimeoutError('body deadline')
                        self.connection.settimeout(remaining)
                        part=self.rfile.read1(min(left,65536))
                        if not part:break
                        chunks.append(part);left-=len(part)
                    raw=b''.join(chunks)
                    self.connection.settimeout(7)
                    if len(raw)!=length:raise ProtocolError(400,'incomplete body')
                    payload=read_json(raw.decode('utf-8'))
                    if self.path=='/personalization/v2/reminders' and owner.session:
                        value=owner.session.accept(payload,available=owner.input_healthy)
                        self.reply(200,value)
                    elif self.path=='/personalization/v2/results' and owner.store.role=='peer':
                        self.reply(200,owner.store.accept_result(payload))
                    elif self.path=='/text/v1/answers' and owner.session:
                        if not isinstance(payload,dict):raise ProtocolError(400,'object required')
                        value=owner.session.answer(string(payload.get('event_id'),'event_id',128),payload.get('text'))
                        self.reply(200 if value else 202,value or {'disposition':'clarification_pending','mode':'text'})
                    else:
                        raise ProtocolError(404,'unknown endpoint')
                except ProtocolError as error:self.reply(error.code,{'error':str(error)})
                except (ValueError,UnicodeError,RecursionError):self.reply(400,{'error':'invalid JSON or field'})
                except sqlite3.Error:self.reply(503,{'error':'storage unavailable'})
                except (BrokenPipeError,ConnectionResetError,socket.timeout):pass
        try:self.http=ThreadingHTTPServer((host,port),Handler)
        except BaseException:self._lease.close();raise
        # Drain bounded handlers before releasing the process lock on shutdown.
        self.http.daemon_threads=False
        self.url='http://127.0.0.1:'+str(self.http.server_port)
        self.thread=None

    def start(self):
        self.thread=threading.Thread(target=self.http.serve_forever,kwargs={'poll_interval':.05},daemon=True)
        self.thread.start()

    def close(self):
        if self.thread:
            self.http.shutdown();self.thread.join(timeout=8)
        self.http.server_close();self._lease.close()


def run_demo(workdir, *, model_url=None, model_id='qwen25-15b-q4km'):
    """Real loopback HTTP, synthetic text; no fabricated speed or device claims."""
    root=Path(workdir).resolve();root.mkdir(parents=True,exist_ok=False)
    device='v5-synthetic-device'
    model=Store(root/'model.sqlite',device,'model')
    peer=Store(root/'peer.sqlite',device,'peer')
    client=SemanticIntentClient(model_url,model_id) if model_url else None
    backend_attempts=[];decisions=[]
    def classify(text,*,timeout):
        def infer(value):
            backend_attempts.append(value)
            return client.classify(value,timeout=timeout) if client else {'intent':'unclear'}
        decision=classify_reply(text,infer)
        decisions.append(decision)
        return decision
    session=Session(model,classify)
    servers=[]
    output={'synthetic':True,'personalization_peer':'simulated','transport':'real_loopback_HTTP',
            'mode':'text_with_HTTP_model_backend' if client else 'text_rules_with_stub','cases':[]}
    try:
        for store,engine in ((model,session),(peer,None)):
            server=Server(store,engine);server.start();servers.append(server)
        for index,text in enumerate(('我现在没事，谢谢关心。','我现在起不来，帮帮我。','我想找人来看看我。'),1):
            now=time.time();event_id='synthetic-v5-'+str(index)
            payload=dict(schema_version='2',event_id=event_id,alert_type='late_wakeup',
                         timestamp=iso(now),expires_at=iso(now+120),reason='合成数据：起床时间偏晚')
            peer.register_reminder(payload)
            flush_outbox(peer,servers[0].url)
            assert not peer.pending()
            prompts=[];responses=[];first_decision=len(decisions);started=time.monotonic()
            for _ in range(2):
                action=session.tick(event_id)
                assert action and action['kind']=='prompt'
                print(json.dumps(action,ensure_ascii=False),flush=True)
                prompts.append(action);session.displayed(event_id)
                code,value=post(servers[0].url+'/text/v1/answers',{'event_id':event_id,'text':text},timeout=7)
                assert code in (200,202),(code,value)
                responses.append({'http_status':code,'body':value})
                if code==200:break
            assert model.event(event_id)['latest'] is not None
            flush_outbox(model,servers[1].url)
            actual=peer.event(event_id)['latest']
            assert actual==model.event(event_id)['latest'] and not model.pending()
            output['cases'].append({'event_id':event_id,'text':text,'prompts':len(prompts),'result':actual,
                                    'policy_decisions':decisions[first_decision:],'http_responses':responses,
                                    'wall_seconds':time.monotonic()-started})
        output['backend_attempts']=len(backend_attempts)
        output['help_tasks']=len(peer.help_tasks())
        output['manual_deliveries']=len(model.failed_deliveries())+len(peer.failed_deliveries())
        (root/'result.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return output
    finally:
        for server in reversed(servers):server.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve',help='start isolated model or simulated personalization role')
    serve.add_argument('--role',choices=('model','peer'),required=True)
    serve.add_argument('--db',required=True);serve.add_argument('--device',required=True)
    serve.add_argument('--port',type=int,required=True);serve.add_argument('--peer-url')
    serve.add_argument('--model-url',default='http://127.0.0.1:18081')
    serve.add_argument('--model-id',default='qwen25-15b-q4km')
    serve.add_argument('--simulate',action='store_true',help='rules plus fixed unclear model stub; not real inference')
    send=sub.add_parser('send',help='persist simulated reminder before first HTTP send')
    send.add_argument('--db',required=True);send.add_argument('--device',required=True)
    send.add_argument('--reminder',required=True);send.add_argument('--target',required=True)
    answer=sub.add_parser('answer',help='submit text for an explicit event; max classifier wait five seconds')
    answer.add_argument('--target',required=True);answer.add_argument('--event-id',required=True);answer.add_argument('--text',required=True)
    demo=sub.add_parser('demo',help='three synthetic text cases over real loopback HTTP')
    demo.add_argument('--workdir',required=True,help='new directory only; includes local databases and result.json')
    demo.add_argument('--model-url',help='omit for explicit model stub; existing loopback model service only')
    demo.add_argument('--model-id',default='qwen25-15b-q4km')
    args=parser.parse_args()
    if args.command=='demo':
        output=run_demo(args.workdir,model_url=args.model_url,model_id=args.model_id)
        print(json.dumps(output,ensure_ascii=False,indent=2));return
    if args.command=='answer':
        code,payload=post(args.target.rstrip('/')+'/text/v1/answers',{'event_id':args.event_id,'text':args.text},timeout=7)
        print(json.dumps({'http_status':code,'body':payload},ensure_ascii=False))
        return
    store=Store(args.db,args.device,'peer' if args.command=='send' else args.role)
    if args.command=='send':
        payload=read_json(Path(args.reminder).read_text(encoding='utf-8-sig'))
        store.register_reminder(payload);flush_outbox(store,args.target)
        print(json.dumps({'registered':payload['event_id'],'pending_now':len(store.pending()),'mode':'simulated_personalization'}))
        return
    if args.peer_url:endpoint(args.peer_url)
    session=None
    if args.role=='model':
        client=SemanticIntentClient(args.model_url,args.model_id)
        def classify(text,*,timeout):
            infer=(lambda value:{'intent':'unclear'}) if args.simulate else (lambda value:client.classify(value,timeout=timeout))
            return classify_reply(text,infer)
        session=Session(store,classify)
    server=Server(store,session,port=args.port)
    stop=threading.Event()
    delivery_thread=None
    try:
        if session:session.recover()
        server.start()
        print(json.dumps({'listening':server.url,'role':args.role,'mode':'text',
                          'classifier':('rules_with_stub' if args.simulate else 'V3_with_real_backend') if session else None,
                          'personalization_peer':'simulated' if args.role=='peer' else 'separate_module'},ensure_ascii=False),flush=True)
        if args.peer_url:
            def deliver():
                while not stop.is_set():
                    try:flush_outbox(store,args.peer_url,stop=stop)
                    except sqlite3.Error:pass  # Durable pending records remain unconfirmed.
                    stop.wait(.25)
            delivery_thread=threading.Thread(target=deliver,daemon=True)
            delivery_thread.start()
        while True:
            if session:
                for event in store.events():
                    if event['latest'] is not None:continue
                    action=session.tick(event['event_id'],input_healthy=server.input_healthy)
                    if action and action.get('kind')=='prompt':
                        try:print(json.dumps(action,ensure_ascii=False),flush=True)
                        except (OSError,UnicodeError):session.displayed(event['event_id'],success=False)
                        else:session.displayed(event['event_id'],input_healthy=server.input_healthy)
            time.sleep(.1)
    except KeyboardInterrupt:pass
    finally:
        stop.set()
        if delivery_thread:delivery_thread.join(timeout=4)
        server.close()


if __name__=='__main__':main()
