"""Process-local preparation gate; never a claim of model understanding quality."""
import queue
import threading
import time


class ModelReadiness:
    def __init__(self,infer,*,warm_timeout=30,probe_timeout=5,retry_seconds=5):
        self.infer=infer
        if min(warm_timeout,probe_timeout,retry_seconds)<=0:raise ValueError('positive budgets required')
        self.warm_timeout,self.probe_timeout,self.retry_seconds=warm_timeout,probe_timeout,retry_seconds
        self._lock=threading.Lock();self._attempt_lock=threading.Lock();self._backend_lock=threading.Lock()
        self._epoch=0;self._worker=None
        self._stop=None
        self._state={'state':'cold','last_error':None,'warm_seconds':None,'probe_seconds':None,
                     'warm_calls':0,'probe_calls':0,'classification_calls':0}

    @property
    def ready(self):
        with self._lock:return self._state['state']=='ready'

    def snapshot(self):
        with self._lock:return {**self._state,'ready':self._state['state']=='ready'}

    def accept(self,operation):
        with self._lock:return operation(self._state['state']=='ready')

    def invalidate(self,reason='backend_failure'):
        with self._lock:
            self._epoch+=1
            self._state.update(state='failed',last_error=reason)

    def _backend(self,text,timeout,stage):
        if not self._backend_lock.acquire(blocking=False):raise TimeoutError('backend busy')
        try:
            with self._lock:self._state[stage]+=1
            return self.infer(text,timeout=timeout)
        finally:self._backend_lock.release()

    def classify(self,text,*,timeout=5):
        if not self.ready:raise TimeoutError('backend not prepared')
        try:return self._backend(text,timeout,'classification_calls')
        except Exception as error:
            self.invalidate(type(error).__name__)
            raise

    def _call(self,text,timeout,stage):
        if self._worker is not None and self._worker.is_alive():raise TimeoutError('previous backend still running')
        output=queue.Queue(maxsize=1)
        def work():
            try:output.put((True,self._backend(text,timeout,stage)))
            except Exception as error:output.put((False,error))
        self._worker=threading.Thread(target=work,daemon=True);self._worker.start()
        try:good,value=output.get(timeout=timeout)
        except queue.Empty as error:raise TimeoutError('preparation deadline') from error
        self._worker.join(timeout=.01)
        if not good:raise value
        if not isinstance(value,dict) or value.get('intent') not in ('okay','needs_help','unclear'):
            raise ValueError('invalid classification result')
        return value

    def warm(self):
        if not self._attempt_lock.acquire(blocking=False):return False
        try:
            with self._lock:
                epoch=self._epoch
                self._state.update(state='warming',last_error=None,warm_seconds=None,probe_seconds=None)
            timings={}
            try:
                for key,text,budget in (
                    ('warm_seconds','这是一条独立的预热测试，我没有听懂你的问题。',self.warm_timeout),
                    ('probe_seconds','我现在需要有人过来帮我一下。',self.probe_timeout)):
                    stage='warm_calls' if key=='warm_seconds' else 'probe_calls'
                    started=time.monotonic();self._call(text,budget,stage);timings[key]=time.monotonic()-started
                    with self._lock:
                        if epoch!=self._epoch or (self._stop and self._stop.is_set()):return False
                with self._lock:
                    if epoch!=self._epoch or (self._stop and self._stop.is_set()):return False
                    self._state.update(state='ready',**timings)
                return True
            except Exception as error:
                with self._lock:
                    if epoch==self._epoch:self._state.update(state='failed',last_error=type(error).__name__,**timings)
                return False
        finally:self._attempt_lock.release()

    def run(self,stop):
        self._stop=stop
        try:
            while not stop.is_set():
                if not self.ready:self.warm()
                stop.wait(self.retry_seconds if not self.ready else .1)
        finally:self.invalidate('stopped')
