"""Care speech through an existing 48 kHz mono S16 output, with intercom priority."""
from collections import deque
from pathlib import Path
import threading
import time
import wave


class CareAudioPlayer:
    def __init__(self, directory, writer, output_ready, *, wait=None, clock=None):
        self.writer,self.output_ready=writer,output_ready
        self.clock=clock or time.monotonic
        self._lock=threading.RLock();self._stop=threading.Event()
        self.wait=wait or self._stop.wait
        self._thread=None;self._busy_until=0;self._latest={};self._seen=deque(maxlen=256)
        self._queue=deque();self._clips={}
        for text_id in ('sedentary.l0','sedentary.l1'):
            with wave.open(str(Path(directory)/(text_id+'.wav')),'rb') as stream:
                if (stream.getnchannels()!=1 or stream.getsampwidth()!=2 or stream.getframerate()!=48000
                        or stream.getcomptype()!='NONE' or not 0<stream.getnframes()<=48000*30):
                    raise ValueError('care speech requires 48kHz mono S16 PCM, at most 30 seconds')
                self._clips[text_id]=stream.readframes(stream.getnframes())

    def start(self):
        with self._lock:
            if self._thread is None:
                self._thread=threading.Thread(target=self._run,name='care-speech',daemon=True)
                self._thread.start()

    def enqueue(self, message):
        if (message.get('text_id') not in self._clips or not message.get('person_id')
                or not message.get('event_id') or type(message.get('revision')) is not int or message['revision']<1):
            return False
        key=(message['event_id'],message['revision'])
        with self._lock:
            if self._stop.is_set() or key in self._seen or len(self._queue)>=8:return False
            self._seen.append(key);self._latest[message['person_id']]=key
            self._queue.append((dict(message),self.clock()));return True

    def cancel(self, person):
        with self._lock:self._latest.pop(person,None)

    def handle_steps(self, steps):
        for step in steps:
            if step.get('snapshot',{}).get('phase')=='IDLE':self.cancel(step['person_id'])
            else:
                for message in step.get('broadcasts',[]):self.enqueue(message)

    def intercom(self, data):
        with self._lock:
            self._busy_until=self.clock()+0.4
            self.writer(data)

    def play_next(self):
        with self._lock:
            if (self._stop.is_set() or not self._queue or self.clock()<self._busy_until
                    or not self.output_ready()):return False
            message,queued_at=self._queue.popleft()
            key=(message['event_id'],message['revision']);person=message['person_id']
            if self._latest.get(person)!=key or self.clock()-queued_at>30:return False
        pcm=self._clips[message['text_id']]
        for offset in range(0,len(pcm),1920):
            with self._lock:
                latest=self._latest.get(person)
                if (self._stop.is_set() or self.clock()<self._busy_until or latest is None
                        or latest[0]!=message['event_id'] or not self.output_ready()):return False
                self.writer(pcm[offset:offset+1920].ljust(1920,b'\0'))
            if self.wait(.02):return False
        return True

    def _run(self):
        while not self._stop.is_set():
            try:self.play_next()
            except Exception:
                # A failed optional speaker must not terminate camera/detection work.
                self._stop.wait(.2)
            self._stop.wait(.02)

    def close(self):
        self._stop.set()
        with self._lock:self._queue.clear();self._latest.clear()
        if self._thread is not None and self._thread is not threading.current_thread():self._thread.join(timeout=1)
