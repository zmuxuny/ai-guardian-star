"""Explicit live-only outbox transport, separated from all legacy alert topics."""
import json
import threading


class MqttCareSender:
    TOPICS = {'reminder': 'ai_guardian/care/reminders', 'feedback': 'ai_guardian/care/feedback'}
    def __init__(self, client):
        self.client = client

    def __call__(self, message):
        if message['mode'] != 'live' or message['message_type'] not in self.TOPICS:
            raise ValueError('shadow/unrecognized messages cannot enter live transport')
        payload = {key: message[key] for key in
                   ('message_id','event_id','person_id','model_version','message_type','revision','payload')}
        receipt = self.client.publish(self.TOPICS[message['message_type']],
                                      json.dumps(payload, ensure_ascii=False, allow_nan=False), qos=1)
        if receipt.rc != 0:
            return False
        receipt.wait_for_publish(timeout=3)
        return receipt.is_published() is True


class DeliveryWorker:
    def __init__(self, runtime, sender):
        if runtime.config.mode != 'live' or not runtime.config.sync_enabled:
            raise ValueError('delivery requires explicit live mode and sync_enabled')
        self.runtime, self.sender = runtime, sender
        self.stop_event = threading.Event()
        self.thread = None

    def step(self):
        return self.runtime.flush(self.sender)

    def start(self):
        def loop():
            while not self.stop_event.is_set():
                try:
                    self.step()
                except Exception as exc:
                    print(f'[Care] sync_failed code={type(exc).__name__}')
                self.stop_event.wait(5)
        self.thread = threading.Thread(target=loop, name='care-delivery', daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=5)
