import os
import pyaudio
import threading
import queue
import numpy as np
from ctypes import *
from contextlib import contextmanager


ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)


def py_error_handler(filename, line, function, err, fmt):
    pass


c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)


@contextmanager
def no_alsa_error():
    try:
        asound = cdll.LoadLibrary("libasound.so")
        asound.snd_lib_error_set_handler(c_error_handler)
        yield
        asound.snd_lib_error_set_handler(None)
    except Exception:
        yield


AUDIO_RATE = 48000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_SAMPLES_PER_FRAME = int(os.getenv("AI_GUARDIAN_AUDIO_FRAME_SAMPLES", "1920"))
AUDIO_MAX_PLAY_BUFFER_BYTES = int(AUDIO_RATE * 2 * 0.18)
AUDIO_TRIM_PLAY_BUFFER_BYTES = int(AUDIO_RATE * 2 * 0.08)
FORCE_AUDIO_INPUT_INDEX = int(os.getenv("AI_GUARDIAN_AUDIO_INPUT_INDEX", "-1"))
FORCE_AUDIO_OUTPUT_INDEX = int(os.getenv("AI_GUARDIAN_AUDIO_OUTPUT_INDEX", "-1"))
INPUT_CHANNEL_MODE = os.getenv("AI_GUARDIAN_AUDIO_INPUT_CHANNEL_MODE", "right").strip().lower()
INPUT_NOISE_GATE = int(os.getenv("AI_GUARDIAN_AUDIO_NOISE_GATE", "700"))

record_queue = queue.Queue(maxsize=200)
play_buffer = bytearray()
play_lock = threading.Lock()

_pyaudio = None
_in_stream = None
_out_stream = None
_stop_event = threading.Event()
_audio_cleanup_lock = threading.Lock()
_audio_status = {
    "input_enabled": False,
    "output_enabled": False,
    "input_device": None,
    "output_device": None,
    "input_device_index": None,
    "output_device_index": None,
}
_input_channels = 1


def _clean_input_audio(mono):
    if mono.size == 0:
        return mono

    # Keep callback CPU cost low: remove DC offset and apply a simple noise gate.
    src = mono.astype(np.float32)
    out = src - src.mean()

    gate = float(INPUT_NOISE_GATE)
    out[np.abs(out) < gate] = 0.0
    return np.clip(out, -32768, 32767).astype(np.int16)


def _record_cb(in_data, frame_count, time_info, status):
    if not _stop_event.is_set() and in_data:
        try:
            payload = in_data
            if _input_channels > 1:
                samples = np.frombuffer(in_data, dtype=np.int16)
                if samples.size >= _input_channels:
                    frames = samples.reshape(-1, _input_channels)
                    if INPUT_CHANNEL_MODE == "right" and _input_channels >= 2:
                        mono = frames[:, 1].astype(np.int16)
                    elif INPUT_CHANNEL_MODE == "avg":
                        mono = frames.mean(axis=1).astype(np.int16)
                    else:
                        mono = frames[:, 0].astype(np.int16)
                    payload = _clean_input_audio(mono).tobytes()
            elif _input_channels == 1:
                mono = np.frombuffer(in_data, dtype=np.int16)
                payload = _clean_input_audio(mono).tobytes()
            record_queue.put(payload, block=False)
        except Exception:
            pass
    return (None, pyaudio.paContinue)


def _play_cb(in_data, frame_count, time_info, status):
    bytes_needed = frame_count * 2
    data = b"\x00" * bytes_needed
    if not _stop_event.is_set():
        with play_lock:
            if len(play_buffer) >= bytes_needed:
                data = bytes(play_buffer[:bytes_needed])
                del play_buffer[:bytes_needed]
            elif len(play_buffer) > 0:
                part = bytes(play_buffer)
                data = part + b"\x00" * (bytes_needed - len(part))
                del play_buffer[:]
    return (data, pyaudio.paContinue)


def _collect_devices(pa):
    devices = []
    for i in range(pa.get_device_count()):
        try:
            info = pa.get_device_info_by_index(i)
            devices.append({
                "index": i,
                "name": info.get("name", ""),
                "input": int(info.get("maxInputChannels", 0)),
                "output": int(info.get("maxOutputChannels", 0)),
                "rate": int(info.get("defaultSampleRate", 0)),
            })
        except Exception:
            continue
    return devices


def _pick_input_device(pa, devices):
    if FORCE_AUDIO_INPUT_INDEX >= 0:
        for dev in devices:
            if dev["index"] == FORCE_AUDIO_INPUT_INDEX and dev["input"] > 0:
                return dev["index"]

    preferred_names = ("USB2.0 DEVICE", "MIC", "HEADSET", "AB13X", "USB", "WEBCAM", "CAMERA")
    for dev in devices:
        if dev["input"] > 0 and any(key in dev["name"].upper() for key in preferred_names):
            return dev["index"]

    for getter in (pa.get_default_input_device_info,):
        try:
            return getter()["index"]
        except Exception:
            pass

    for dev in devices:
        if dev["input"] > 0:
            return dev["index"]

    return None


def _pick_output_device(pa, devices):
    if FORCE_AUDIO_OUTPUT_INDEX >= 0:
        for dev in devices:
            if dev["index"] == FORCE_AUDIO_OUTPUT_INDEX and dev["output"] > 0:
                return dev["index"]

    keywords = ("USB", "AB13X", "SPEAKER", "OUTPUT", "HEADSET")
    for dev in devices:
        if dev["output"] > 0 and any(key in dev["name"].upper() for key in keywords):
            return dev["index"]

    for getter in (pa.get_default_output_device_info,):
        try:
            return getter()["index"]
        except Exception:
            pass

    for dev in devices:
        if dev["output"] > 0:
            return dev["index"]

    return None


def _device_name(devices, index):
    for dev in devices:
        if dev["index"] == index:
            return dev["name"]
    return None


def start_audio_service():
    global _pyaudio, _in_stream, _out_stream, _audio_status, _input_channels

    if _pyaudio is not None:
        return

    print("🎤 [Hardware] 初始化音频系统...")
    _stop_event.clear()
    _audio_status = {
        "input_enabled": False,
        "output_enabled": False,
        "input_device": None,
        "output_device": None,
        "input_device_index": None,
        "output_device_index": None,
    }

    with no_alsa_error():
        try:
            _pyaudio = pyaudio.PyAudio()
            devices = _collect_devices(_pyaudio)
            input_idx = _pick_input_device(_pyaudio, devices)
            output_idx = _pick_output_device(_pyaudio, devices)

            print(f"[Audio] 检测到设备数: {len(devices)}")
            for dev in devices:
                print(
                    f"[Audio] Device[{dev['index']}] name={dev['name']} "
                    f"in={dev['input']} out={dev['output']} rate={dev['rate']}"
                )
            print(f"[Audio] 选择输入设备: {input_idx} {_device_name(devices, input_idx)}")
            print(f"[Audio] 选择输出设备: {output_idx} {_device_name(devices, output_idx)}")

            if input_idx is not None:
                selected_input = next((dev for dev in devices if dev["index"] == input_idx), None)
                _input_channels = 2 if selected_input and int(selected_input.get("input", 0)) >= 2 else 1
                _in_stream = _pyaudio.open(
                    format=AUDIO_FORMAT,
                    channels=_input_channels,
                    rate=AUDIO_RATE,
                    input=True,
                    input_device_index=input_idx,
                    frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
                    stream_callback=_record_cb,
                )
                _in_stream.start_stream()
                _audio_status["input_enabled"] = True
                _audio_status["input_device"] = _device_name(devices, input_idx)
                _audio_status["input_device_index"] = input_idx
                print(
                    f"[Audio] 输入声道数: {_input_channels} | 下混模式: {INPUT_CHANNEL_MODE} | "
                    f"frames_per_buffer={AUDIO_SAMPLES_PER_FRAME}"
                )
            else:
                print("[Audio] 未找到可用输入设备，录音功能关闭。")

            if output_idx is not None:
                _out_stream = _pyaudio.open(
                    format=AUDIO_FORMAT,
                    channels=AUDIO_CHANNELS,
                    rate=AUDIO_RATE,
                    output=True,
                    output_device_index=output_idx,
                    frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
                    stream_callback=_play_cb,
                )
                _out_stream.start_stream()
                _audio_status["output_enabled"] = True
                _audio_status["output_device"] = _device_name(devices, output_idx)
                _audio_status["output_device_index"] = output_idx
            else:
                try:
                    from ascend_audio_output import AscendAudioOutput
                    def output_failed(error):
                        _audio_status["output_enabled"] = False
                        print(f"[Audio] 板载耳机播放失败: {error}")
                    _out_stream = AscendAudioOutput(_play_cb, output_failed)
                    _audio_status["output_device"] = "Ascend MIPI headphone (3.5mm)"
                    _audio_status["output_enabled"] = True
                    _out_stream.start_stream()
                except Exception as error:
                    _audio_status["output_enabled"] = False
                    print(f"[Audio] 板载耳机输出不可用: {error}")

            if not _audio_status["input_enabled"] and not _audio_status["output_enabled"]:
                print("[Audio] 没有可用音频设备，语音服务保持空闲。")
            else:
                print(
                    f"[Audio] 音频服务已启动 | "
                    f"input={_audio_status['input_enabled']} output={_audio_status['output_enabled']}"
                )

            _stop_event.wait()
        except Exception as e:
            print(f"❌ 音频启动异常: {e}")
        finally:
            stop_audio_service()


def stop_audio_service():
    global _pyaudio, _in_stream, _out_stream
    _stop_event.set()
    with _audio_cleanup_lock:
        streams = (_in_stream, _out_stream)
        _in_stream = None
        _out_stream = None
        instance = _pyaudio
        _pyaudio = None
        for stream in streams:
            if stream is None:
                continue
            try:
                if stream.is_active():
                    stream.stop_stream()
            except Exception:
                pass
            try:
                stream.close()
            except Exception:
                pass
        if instance is not None:
            try:
                instance.terminate()
            except Exception:
                pass


def get_audio_frame():
    if not _audio_status["input_enabled"]:
        return None
    try:
        return record_queue.get(block=True, timeout=0.01)
    except Exception:
        return None


def put_audio_frame(data):
    if not data or not _audio_status["output_enabled"]:
        return
    with play_lock:
        play_buffer.extend(data)
        if len(play_buffer) > AUDIO_MAX_PLAY_BUFFER_BYTES:
            trim = len(play_buffer) - AUDIO_TRIM_PLAY_BUFFER_BYTES
            del play_buffer[:trim]


def get_audio_status():
    return dict(_audio_status)
