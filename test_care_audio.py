"""Hardware-free tests of the real care/intercom playback adapter."""
from pathlib import Path
import ast
import tempfile
import unittest
import wave

from src.care_audio import CareAudioPlayer


class CareAudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.frames=[]
        for name in ('sedentary.l0','sedentary.l1'):
            with wave.open(str(self.root/(name+'.wav')),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(48000)
                stream.writeframes(b'\x01\x00'*2880)
        self.player=CareAudioPlayer(self.root,self.frames.append,lambda:True,wait=lambda seconds:False)
        self.addCleanup(self.player.close)

    def message(self,person='p1',event='e1',revision=1):
        return dict(person_id=person,event_id=event,revision=revision,text_id='sedentary.l0')

    def test_existing_output_receives_paced_pcm_and_duplicate_is_not_replayed(self):
        message=self.message()
        self.assertTrue(self.player.enqueue(message));self.assertFalse(self.player.enqueue(message))
        self.assertTrue(self.player.play_next())
        self.assertEqual([len(frame) for frame in self.frames],[1920]*3)

    def test_clear_cancels_only_that_person_and_skips_obsolete_episode(self):
        self.player.enqueue(self.message());self.player.enqueue(self.message('p2','e2'))
        self.player.cancel('p1')
        self.player.play_next();self.assertEqual(self.frames,[])
        self.player.play_next();self.assertEqual(len(self.frames),3)

    def test_intercom_preempts_current_care_without_opening_another_output(self):
        def write(frame):
            self.frames.append(frame)
            if len(self.frames)==1:self.player.intercom(b'intercom')
        self.player.writer=write;self.player.enqueue(self.message())
        self.player.play_next()
        self.assertEqual(len(self.frames),2)
        self.assertEqual(self.frames[-1],b'intercom')

    def test_output_unavailable_does_not_claim_audio_was_played(self):
        self.player.output_ready=lambda:False;self.player.enqueue(self.message())
        self.assertFalse(self.player.play_next());self.assertEqual(self.frames,[])

    def test_unknown_text_and_invalid_wave_do_not_enter_queue(self):
        message=self.message();message['text_id']='../../private'
        self.assertFalse(self.player.enqueue(message))
        with wave.open(str(self.root/'sedentary.l0.wav'),'wb') as stream:
            stream.setnchannels(2);stream.setsampwidth(2);stream.setframerate(16000);stream.writeframes(b'\0'*8)
        with self.assertRaises(ValueError):CareAudioPlayer(self.root,self.frames.append,lambda:True)

    def test_runtime_steps_cancel_cleared_person_before_queuing_new_messages(self):
        self.player.enqueue(self.message())
        self.player.handle_steps([dict(person_id='p1',snapshot=dict(phase='IDLE'),broadcasts=[])])
        self.player.play_next();self.assertEqual(self.frames,[])

    def test_detection_result_survives_audio_failure_and_intercom_uses_same_writer(self):
        from types import SimpleNamespace
        source=Path(__file__).with_name('src')/'ascend_board_server.py'
        tree=ast.parse(source.read_text(encoding='utf-8-sig'))
        names={'dispatch_care_detection','dispatch_care_audio','play_intercom_audio'}
        selected=ast.Module(body=[node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name in names],type_ignores=[])
        class FailedPlayer:
            def handle_steps(self,steps):raise OSError('speaker unavailable')
            def intercom(self,data):self.data=data
        player=FailedPlayer();namespace={'care_audio_player':player}
        exec(compile(selected,str(source),'exec'),namespace)
        expected=dict(mode='shadow',states=[{'person_id':'p1'}],event_refs={},record_refs=[])
        runtime=SimpleNamespace(process_frame=lambda alerts,events:expected)
        self.assertIs(namespace['dispatch_care_detection'](runtime,[],{}),expected)
        namespace['play_intercom_audio'](b'voice');self.assertEqual(player.data,b'voice')


if __name__=='__main__':unittest.main()
