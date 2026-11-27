import threading
import time
import unittest

from src.local_model_readiness import ModelReadiness


class ReadinessTests(unittest.TestCase):
    def test_warmup_then_five_second_probe_before_ready(self):
        calls=[]
        gate=ModelReadiness(lambda text,timeout:calls.append((text,timeout)) or {'intent':'okay'})
        self.assertFalse(gate.ready)
        self.assertTrue(gate.warm())
        self.assertTrue(gate.ready)
        self.assertEqual([x[1] for x in calls],[30,5])
        self.assertEqual(gate.snapshot()['state'],'ready')

    def test_failure_and_invalid_output_do_not_open_gate(self):
        for value in ({'intent':'invalid'},None):
            gate=ModelReadiness(lambda text,timeout:value)
            self.assertFalse(gate.warm());self.assertFalse(gate.ready)
        def fail(text,timeout):raise TimeoutError()
        gate=ModelReadiness(fail)
        self.assertFalse(gate.warm());self.assertEqual(gate.snapshot()['last_error'],'TimeoutError')

    def test_invalidate_during_warmup_cannot_publish_stale_ready(self):
        entered=threading.Event();release=threading.Event()
        def blocked(text,timeout):entered.set();release.wait(2);return {'intent':'unclear'}
        gate=ModelReadiness(blocked)
        worker=threading.Thread(target=gate.warm);worker.start();self.assertTrue(entered.wait(1))
        gate.invalidate('restart');release.set();worker.join(2)
        self.assertFalse(gate.ready)

    def test_noncooperative_backend_is_bounded_without_accumulating_workers(self):
        release=threading.Event();self.addCleanup(release.set);calls=[]
        def stuck(text,timeout):calls.append(text);release.wait(2);return {'intent':'okay'}
        gate=ModelReadiness(stuck,warm_timeout=.05,probe_timeout=.05)
        start=time.monotonic();self.assertFalse(gate.warm());self.assertLess(time.monotonic()-start,.5)
        self.assertFalse(gate.warm());self.assertEqual(len(calls),1)

    def test_retry_and_stop_and_new_process_gate(self):
        calls=[]
        def infer(text,timeout):
            calls.append(text)
            if len(calls)==1:raise ConnectionError()
            return {'intent':'needs_help'}
        gate=ModelReadiness(infer,retry_seconds=.02)
        stop=threading.Event();worker=threading.Thread(target=gate.run,args=(stop,));worker.start()
        try:
            for _ in range(100):
                if gate.ready:break
                time.sleep(.01)
            self.assertTrue(gate.ready)
        finally:stop.set();worker.join(1)
        self.assertFalse(gate.ready)
        self.assertFalse(ModelReadiness(infer).ready)
