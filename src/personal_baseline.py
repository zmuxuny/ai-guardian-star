"""Bounded, opt-in private posture writer; no sensors, audio, MQTT or network."""
from copy import deepcopy
from queue import Queue, Empty, Full
import threading
import time


class PersonalBaselineWorker:
    def __init__(self, stores, mode, camera_revision):
        self.stores, self.mode, self.camera = stores, mode, camera_revision
        self._queue = Queue(maxsize=32)
        self._state, self._execute = threading.Lock(), threading.Lock()
        self._closed = False
        self._generation = {p:0 for p in stores}
        self._disabled, self._last = set(), {}
        self._counts = dict(accepted=0,dropped=0,errors=0)
        self._thread = threading.Thread(target=self._run,name='personal-posture',daemon=True)
        self._thread.start()

    def _count(self, name):
        self._counts[name] = min(1000000000,self._counts[name]+1)

    def error(self):
        with self._state:
            self._count('errors')

    def diagnostics(self):
        with self._state:
            return dict(self._counts,queued=self._queue.qsize())

    def _submit(self, kind, person, value, at=None):
        with self._state:
            if self._closed or person not in self.stores or person in self._disabled:
                return False
            if kind=='hist' and (self.camera is None or at-self._last.get(person,float('-inf'))<1):
                return False
            try:
                self._queue.put_nowait((kind,person,self._generation[person],deepcopy(value),at))
            except Full:
                self._count('dropped')
                return False
            if kind=='hist':
                self._last[person]=at
            self._count('accepted')
            return True

    def event(self, person, ref, feature, guards=None):
        return self._submit('event',person,(ref,feature,guards))

    def observe(self, person, feature, at):
        return self._submit('hist',person,feature,at)

    def suspend(self, person):
        # Wait for the one in-flight writer before the caller erases its DB rows.
        with self._execute, self._state:
            self._generation[person]+=1
            self._disabled.add(person)
            self._last.pop(person,None)

    def resume(self, person):
        with self._state:
            self._generation[person]+=1
            self._disabled.discard(person)
            self._last.pop(person,None)

    def _run(self):
        while True:
            try:
                kind,person,generation,value,at = self._queue.get(timeout=.1)
            except Empty:
                with self._state:
                    if self._closed:
                        return
                continue
            try:
                with self._execute:
                    with self._state:
                        valid = generation==self._generation[person] and person not in self._disabled
                    if not valid:
                        continue
                    store = self.stores[person]
                    if store.erased():
                        continue
                    if kind=='event':
                        ref,feature,guards=value
                        store.create_event(ref)
                        store.capture_event(self.mode,ref['event_id'],feature,self.camera,guards=guards)
                    else:
                        store.observe_histogram(self.mode,value,self.camera,at)
                    store.maintain(self.mode)
            except Exception:
                self.error()
            finally:
                self._queue.task_done()

    def flush(self, timeout=10):
        deadline = time.monotonic()+timeout
        with self._queue.all_tasks_done:
            while self._queue.unfinished_tasks:
                remaining=deadline-time.monotonic()
                if remaining<=0:
                    return False
                self._queue.all_tasks_done.wait(remaining)
        return True

    def close(self, timeout=10):
        with self._state:
            self._closed=True
        self._thread.join(timeout)
        return not self._thread.is_alive()
