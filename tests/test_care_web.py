"""Public display is bounded to currently visible faces, never private care IDs."""
import ast
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

SERVER = Path(__file__).resolve().parents[1] / 'src/ascend_board_server.py'
sys.path.insert(0, str(SERVER.parent))


def load_display():
    node = next(n for n in ast.parse(SERVER.read_text(encoding='utf-8')).body
                if getattr(n, 'name', '') == 'care_display_snapshot')
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SERVER), 'exec'), namespace)
    return namespace[node.name]


class CareDisplayTests(unittest.TestCase):
    def setUp(self):
        self.display = load_display()
        self.state = dict(state='L0', phase='L0', seated_seconds=12.5, level='L0',
                          counts={'L0': 1, 'L1': 0}, uncertainty_reason=None)
        self.runtime = SimpleNamespace(
            config=SimpleNamespace(mode='shadow', person_ids=('private-id','hidden-id'), face_label_ids={'zy': 'private-id', 'other': 'hidden-id'}),
            state=lambda person: self.state.copy(),
            shadow_broadcasts=lambda: [dict(person_id='private-id', event_id='private-event',
                                           level='L0', text='起来活动一下', wall_time='2026-11-19T20:00:00+08:00'),
                                      dict(person_id='hidden-id', text='hidden history')])

    def test_off_does_not_return_stale_people(self):
        self.assertEqual(self.display(None, [{'label':'known:zy'}], False),
                         {'mode':'off', 'audio_available':False, 'people':[]})
        self.assertEqual('unavailable', self.display(None, [], False, initialization_failed=True)['mode'])

    def test_live_and_recovered_state_have_reminder_without_shadow_history(self):
        self.runtime.config.mode='live'
        result=self.display(self.runtime, [{'label':'known:zy'}], True)
        self.assertIsNotNone(result['people'][0]['reminder'])
        self.assertEqual('L0', result['people'][0]['reminder']['level'])
        self.runtime.config.mode='shadow'
        self.runtime.shadow_broadcasts=lambda: []
        self.assertIsNotNone(self.display(self.runtime, [{'label':'known:zy'}], False)['people'][0]['reminder'])

    def test_actual_runtime_reminder_survives_restart(self):
        from care_runtime import CareRuntime, RuntimeConfig
        from sedentary_care import Config, VirtualClock
        with tempfile.TemporaryDirectory() as tmp:
            clock=VirtualClock()
            config=RuntimeConfig(Path(tmp)/'care.db', ('p1',), 'test-web', mode='live',
                                 face_label_ids={'demo':'p1'}, machine=Config(l0_seconds=2, quiet_start=None, quiet_end=None))
            runtime=CareRuntime(config, clock=clock)
            try:
                alert={'face_label':'known:demo', 'is_sitting':True, 'id':1}
                runtime.on_detection([alert], {})
                clock.advance(2)
                runtime.on_detection([alert], {})
                self.assertEqual('L0', self.display(runtime, [{'label':'known:demo'}], True)['people'][0]['reminder']['level'])
            finally:
                runtime.close()
            runtime=CareRuntime(config, clock=clock)
            try:
                self.assertIsNotNone(self.display(runtime, [{'label':'known:demo'}], True)['people'][0]['reminder'])
            finally:
                runtime.close()

    def test_only_visible_registered_faces_and_allowlisted_fields(self):
        result = self.display(self.runtime, [{'label':'known:zy'}, {'label':'stranger'}, {'label':'known:zy'}], True)
        self.assertEqual(1, len(result['people']))
        person = result['people'][0]
        self.assertEqual('zy', person['name'])
        self.assertEqual('起来活动一下', person['reminder']['text'])
        self.assertEqual({'mode','audio_available','people'}, set(result))
        self.assertNotIn('private-', str(result))
        self.assertNotIn('hidden', str(result))
        self.assertNotIn('event_id', str(result))

    def test_reset_hides_old_reminder_and_absence_hides_person(self):
        self.state.update(level=None, counts={'L0':0,'L1':0}, seated_seconds=0)
        self.assertIsNone(self.display(self.runtime, [{'label':'known:zy'}], False)['people'][0]['reminder'])
        self.assertEqual([], self.display(self.runtime, [], False)['people'])

    def test_read_failure_is_unavailable_instead_of_off(self):
        def fail(_):
            raise RuntimeError('private diagnostic')
        self.runtime.state = fail
        result = self.display(self.runtime, [{'label':'known:zy'}], False)
        self.assertEqual('unavailable', result['mode'])
        self.assertNotIn('private diagnostic', str(result))


if __name__ == '__main__':
    unittest.main()
