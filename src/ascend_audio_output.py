"""48 kHz mono S16 playback through the Orange Pi AI Pro headphone jack."""
import ctypes
from pathlib import Path
import threading
import time


class AscendAudioOutput:
    def __init__(self, callback, on_error):
        self._callback = callback
        self._on_error = on_error
        self._stop = threading.Event()
        self._thread = None
        self._lib = ctypes.CDLL(str(Path(__file__).with_name('libguardian_audio.so')))
        self._lib.guardian_audio_open.argtypes = []
        self._lib.guardian_audio_open.restype = ctypes.c_int
        self._lib.guardian_audio_write.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        self._lib.guardian_audio_write.restype = ctypes.c_int
        self._lib.guardian_audio_close.argtypes = []
        self._lib.guardian_audio_close.restype = None
        self._check(self._lib.guardian_audio_open())

    @staticmethod
    def _check(code):
        if code:
            raise OSError(f'Ascend headphone AO error 0x{code & 0xffffffff:08x}')

    def start_stream(self):
        self._thread = threading.Thread(target=self._play, name='ascend-headphone', daemon=True)
        self._thread.start()

    def _play(self):
        try:
            deadline = time.monotonic()
            while not self._stop.is_set():
                data, _ = self._callback(None, 960, None, None)
                if len(data) != 1920:
                    raise ValueError('Headphone output requires 960 S16 samples')
                pcm = ctypes.create_string_buffer(data)
                self._check(self._lib.guardian_audio_write(pcm, len(data)))
                deadline = max(deadline + 0.02, time.monotonic())
                self._stop.wait(max(0, deadline - time.monotonic()))
        except Exception as exc:
            self._on_error(exc)
        finally:
            self._lib.guardian_audio_close()

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        else:
            self._lib.guardian_audio_close()
