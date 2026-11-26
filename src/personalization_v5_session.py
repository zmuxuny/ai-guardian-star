"""Bounded text session for v5. Call display acknowledgement after real output."""
import queue
import threading
import time
import uuid

from .personalization_v5 import ProtocolError, instant

FIXED_PROMPT = '您好，想问问您现在还好吗，需要帮助吗？'


class Session:
    def __init__(self, store, classify, *, monotonic=None):
        if store.role != 'model':
            raise ValueError('model store required')
        self.store, self.classify = store, classify
        self.monotonic = monotonic or time.monotonic
        self.origins, self.waits, self.late_deadlines = {}, {}, {}
        self._worker = None
        self._worker_lock = threading.Lock()

    def accept(self, payload, *, available=True):
        ack = self.store.accept_reminder(payload, available=available)
        if ack['disposition']=='accepted':
            self.origins[payload['event_id']] = self.monotonic()
        return ack

    def _origin(self, event):
        key = event['event_id']
        if key not in self.origins:
            elapsed = self.store.clock()-event['saved_at']
            # Backwards wall time after restart cannot establish remaining time.
            if elapsed < 0:
                return None
            self.origins[key] = self.monotonic()-elapsed
        return self.origins[key]

    def _track(self, event_id, result):
        if result is not None and event_id not in self.late_deadlines:
            event=self.store.event(event_id)
            if event['late_until'] is not None:
                self.late_deadlines[event_id]=self.monotonic()+max(0,event['late_until']-self.store.clock())
        return result

    def tick(self, event_id, *, input_healthy=True):
        action = []
        def step(event):
            state = event['state']
            if event['latest'] is not None:
                return None
            origin = self._origin(event)
            if origin is None:
                return {'error':'interrupted'}
            now = self.monotonic()
            if now-origin >= 90:
                return {'error':'session_timeout'}
            if state['phase']=='pending' and state['prompt_count']==0 and self.store.clock()>=instant(event['reminder']['expires_at']):
                return {'error':'expired_before_prompt'}
            if state['phase']=='waiting' and not input_healthy:
                return {'error':'input_unavailable'}
            if state['phase']=='waiting' and now>=self.waits[event_id]:
                if state['prompt_count']>=2:
                    return {'response':'unclear' if state['ever_input'] else 'no_response'}
                state['phase']='pending'
            if state['phase']=='pending':
                state.update(phase='prompting',prompt_count=state['prompt_count']+1)
                action.append({'kind':'prompt','text':FIXED_PROMPT,'event_id':event_id,
                               'attempt':state['prompt_count'],'mode':'text'})
            return None
        result = self.store.mutate(event_id,step)
        return self._track(event_id,result) if result is not None else (action[0] if action else None)

    def displayed(self, event_id, *, success=True, input_healthy=True):
        def step(event):
            state = event['state']
            if event['latest'] is not None or state['phase']!='prompting':
                return None
            if not success:
                return {'error':'prompt_failed'}
            if not input_healthy:
                return {'error':'input_unavailable'}
            if self.monotonic()-self._origin(event)>=90:
                return {'error':'session_timeout'}
            state.setdefault('prompted_at', self.store.clock())
            state['phase']='waiting'
            self.waits[event_id]=self.monotonic()+20
            return None
        return self._track(event_id,self.store.mutate(event_id,step))

    def interrupt(self, event_id):
        def step(event):
            return None if event['latest'] else {'error':'interrupted'}
        return self._track(event_id,self.store.mutate(event_id,step))

    def _infer(self, text):
        """One daemon worker at most; a misbehaving backend cannot queue forever."""
        output = queue.Queue(maxsize=1)
        classify = self.classify
        def work():
            try:
                output.put((True, classify(text, timeout=5)))
            except Exception as error:
                output.put((False, error))
        with self._worker_lock:
            if self._worker is not None and self._worker.is_alive():
                raise TimeoutError('classifier still busy')
            self._worker = threading.Thread(target=work,daemon=True)
            self._worker.start()
        try:
            good, value = output.get(timeout=5)
        except queue.Empty as error:
            raise TimeoutError('classification deadline') from error
        if not good:
            raise value
        return value

    def answer(self, event_id, text):
        if not isinstance(text,str) or not text.strip() or len(text)>300:
            raise ProtocolError(400,'nonempty text up to 300 characters required')
        before=self.store.event(event_id)
        origin=self._origin(before)
        if before['latest'] is None and (origin is None or self.monotonic()-origin>=90):
            self._track(event_id,self.store.complete(event_id,error='interrupted' if origin is None else 'session_timeout'))
        received_wall, received_mono = self.store.clock(), self.monotonic()
        token = uuid.uuid4().hex
        skip = []
        def begin(event):
            state = event['state']
            if event['latest']:
                deadline=self.late_deadlines.setdefault(event_id,received_mono+max(0,event['late_until']-received_wall))
                if received_wall>=event['late_until'] or received_mono>=deadline or state.get('window_uncertain'):
                    raise ProtocolError(410,'window closed; independent help/manual route required')
                if event['latest'].get('response')=='needs_help':
                    skip.append(event['latest']);return None
            elif state['phase']!='waiting':
                raise ProtocolError(409,'text channel is not awaiting input')
            if state.get('classifying'):
                raise ProtocolError(503,'classification in progress')
            state.update(ever_input=True,classifying=token)
            if not event['latest']:
                state['phase']='classifying'
            return None
        self.store.mutate(event_id,begin)
        if skip:
            return skip[0]
        try:
            prediction = self._infer(text)
            intent = prediction.get('intent') if isinstance(prediction,dict) else None
            response = {'okay':'ok','needs_help':'needs_help','unclear':'unclear'}.get(intent,'unclear')
        except Exception:
            response = 'unclear'
        if self.monotonic()-received_mono>5:
            response = 'unclear'
        def finish(event):
            state = event['state']
            if state.get('classifying')!=token:
                return None
            state.pop('classifying',None)
            origin = self._origin(event)
            if event['latest']:
                if response in ('ok','needs_help'):
                    return {'response':response,'received_at':received_wall}
                return None
            if origin is None:
                return {'error':'interrupted'}
            if self.monotonic()-origin>=90:
                # Persist timeout first, then permit a timely pre-deadline help
                # input to revise it, exactly as an independently ticking worker.
                return {'error':'session_timeout'}
            if response in ('ok','needs_help'):
                return {'response':response,'received_at':received_wall}
            if state['prompt_count']>=2:
                return {'response':'unclear'}
            state['phase']='pending'
            return None
        saved=self._track(event_id,self.store.mutate(event_id,finish))
        # The input arrived during the active session; finishing within its own
        # classification budget can confirm help after the overall timer fired.
        if saved and saved.get('error_code')=='session_timeout' and response=='needs_help':
            origin=self.origins.get(event_id)
            if origin is not None and received_mono-origin<90:
                saved=self.store.complete(event_id,response='needs_help',received_at=received_wall)
        return saved

    def recover(self):
        """Explicit startup operation; never invoke while another runner owns DB."""
        self.origins.clear();self.waits.clear();self.late_deadlines.clear()
        for item in self.store.events():
            def step(event):
                state=event['state']
                state.pop('classifying',None)
                if self.store.clock()<state.get('last_seen_wall',event['saved_at']):
                    state['window_uncertain']=True
                if event['latest']:
                    return None
                origin=self._origin(event)
                if state['phase']!='pending' or origin is None or state.get('window_uncertain'):
                    return {'error':'interrupted'}
                if self.monotonic()-origin>=90:
                    return {'error':'session_timeout'}
                if self.store.clock()>=instant(event['reminder']['expires_at']):
                    return {'error':'expired_before_prompt'}
                return None
            self._track(item['event_id'],self.store.mutate(item['event_id'],step))
        self.store.pending()  # Persist elapsed delivery deadlines, without sending.
