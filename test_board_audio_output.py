"""Regression checks for the optional Ascend headphone playback backend."""
import importlib.util
from pathlib import Path
import threading
import unittest
from unittest.mock import Mock, patch


spec = importlib.util.spec_from_file_location(
    'ascend_audio_output', Path(__file__).parent / 'deploy/board/ascend_audio_output.py')
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)


class HeadphoneOutputTests(unittest.TestCase):
    def backend(self, callback, errors, result=0):
        lib = Mock()
        lib.guardian_audio_open.return_value = 0
        lib.guardian_audio_write.return_value = result
        with patch.object(audio.ctypes, 'CDLL', return_value=lib):
            output = audio.AscendAudioOutput(callback, errors.append)
        return output, lib

    def test_send_failure_reports_error_and_releases_ao(self):
        errors = []
        output, lib = self.backend(lambda *args: (bytes(1920), 0), errors, -1)
        output.start_stream()
        output._thread.join(1)
        output.close()
        self.assertFalse(output._thread.is_alive())
        self.assertEqual(len(errors), 1)
        self.assertIn('0xffffffff', str(errors[0]))
        lib.guardian_audio_close.assert_called_once()

    def test_wrong_frame_length_is_not_sent(self):
        errors = []
        output, lib = self.backend(lambda *args: (bytes(10), 0), errors)
        output.start_stream()
        output._thread.join(1)
        output.close()
        self.assertIsInstance(errors[0], ValueError)
        lib.guardian_audio_write.assert_not_called()
        lib.guardian_audio_close.assert_called_once()

    def test_close_stops_stream_without_extra_frames(self):
        errors = []
        sent = threading.Event()
        output, lib = self.backend(lambda *args: (bytes(1920), 0), errors)
        def write(pcm, length):
            self.assertEqual(length, 1920)
            sent.set()
            return 0
        lib.guardian_audio_write.side_effect = write
        output.start_stream()
        self.assertTrue(sent.wait(1))
        output.close()
        self.assertFalse(output._thread.is_alive())
        self.assertFalse(errors)
        lib.guardian_audio_close.assert_called_once()

    def test_open_failure_does_not_start_thread(self):
        lib = Mock()
        lib.guardian_audio_open.return_value = -1
        with patch.object(audio.ctypes, 'CDLL', return_value=lib):
            with self.assertRaises(OSError):
                audio.AscendAudioOutput(Mock(), Mock())
        lib.guardian_audio_write.assert_not_called()


if __name__ == '__main__':
    unittest.main()
