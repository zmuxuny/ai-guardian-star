# # ascend_voice_stream.py
# import pyaudio
# import threading
# import queue
# import time

# # --- 音频参数 (必须与 WebRTC/后端 定义的音频帧匹配) ---
# AUDIO_RATE = 16000           # 采样率 (Hz)
# AUDIO_CHANNELS = 1           # 通道数 (单声道)
# AUDIO_FORMAT = pyaudio.paInt16 # 采样格式 (16-bit)
# AUDIO_SAMPLE_WIDTH = pyaudio.get_sample_size(AUDIO_FORMAT) # 2 字节

# # 16000 采样/秒 * 0.02 秒 = 320 采样点 (20ms)
# AUDIO_SAMPLES_PER_FRAME = 320 
# AUDIO_CHUNK_BYTES = AUDIO_SAMPLES_PER_FRAME * AUDIO_SAMPLE_WIDTH

# # --- 队列 ---
# # 录音队列：PyAudio -> 应用程序
# record_queue = queue.Queue(maxsize=50)
# # 播放队列：应用程序 -> PyAudio
# play_queue = queue.Queue(maxsize=50)

# _pyaudio_instance = None
# _input_stream = None
# _output_stream = None
# _stop_event = threading.Event()

# print(f"🎤 [ascend_voice_stream] 模块加载。")

# # --- 录音回调 ---
# def _record_callback(in_data, frame_count, time_info, status):
#     if not _stop_event.is_set():
#         try:
#             record_queue.put(in_data, block=False)
#         except queue.Full:
#             pass # 队列满丢弃
#     return (None, pyaudio.paContinue)

# # --- 播放回调 ---
# def _play_callback(in_data, frame_count, time_info, status):
#     data = b'\x00' * (frame_count * AUDIO_SAMPLE_WIDTH) # 默认静音
#     if not _stop_event.is_set():
#         try:
#             # 从播放队列获取数据，非阻塞
#             # 注意：如果队列里的数据块大小不等于 frame_count，可能需要做缓冲处理
#             # 这里假设网络包大小与硬件buffer大小一致或倍数关系，简化处理
#             if not play_queue.empty():
#                 data = play_queue.get(block=False)
#         except queue.Empty:
#             pass
#     return (data, pyaudio.paContinue)

# def start_audio_service():
#     """初始化并启动 PyAudio 录音和播放流"""
#     global _pyaudio_instance, _input_stream, _output_stream
#     print("🎤 [ascend_voice_stream] 正在启动音频服务...")
    
#     try:
#         _pyaudio_instance = pyaudio.PyAudio()
        
#         # --- 查找输入设备 (保持原逻辑) ---
#         input_device_index = None
#         try:
#             info = _pyaudio_instance.get_host_api_info_by_index(0)
#             for i in range(info.get('deviceCount')):
#                 dev_info = _pyaudio_instance.get_device_info_by_host_api_device_index(0, i)
#                 if ("USB" in dev_info.get('name') or "Microphone" in dev_info.get('name')) and dev_info.get('maxInputChannels') > 0:
#                     input_device_index = i
#                     print(f"🎤 [Input] 找到麦克风: {dev_info.get('name')}")
#                     break
#         except: pass

#         # --- 启动录音流 ---
#         _input_stream = _pyaudio_instance.open(
#             format=AUDIO_FORMAT,
#             channels=AUDIO_CHANNELS,
#             rate=AUDIO_RATE,
#             input=True,
#             input_device_index=input_device_index,
#             frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_record_callback
#         )
#         _input_stream.start_stream()

#         # --- 启动播放流 ---
#         # 通常使用默认输出设备（板载耳机孔或HDMI音频）
#         _output_stream = _pyaudio_instance.open(
#             format=AUDIO_FORMAT,
#             channels=AUDIO_CHANNELS,
#             rate=AUDIO_RATE,
#             output=True,
#             frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_play_callback
#         )
#         _output_stream.start_stream()
        
#         print("🎤 [ascend_voice_stream] 双向音频流已启动。")
#         _stop_event.wait() # 阻塞主线程直到停止

#     except Exception as e:
#         print(f"❌ [ascend_voice_stream] 错误: {e}")
#     finally:
#         stop_audio_service()

# def stop_audio_service():
#     """停止服务"""
#     global _pyaudio_instance, _input_stream, _output_stream
#     _stop_event.set()
    
#     if _input_stream:
#         _input_stream.stop_stream()
#         _input_stream.close()
#     if _output_stream:
#         _output_stream.stop_stream()
#         _output_stream.close()
#     if _pyaudio_instance:
#         _pyaudio_instance.terminate()
#     print("🎤 [ascend_voice_stream] 音频服务已停止。")

# def get_audio_frame():
#     """获取录音数据 (发送给服务器)"""
#     try:
#         return record_queue.get(block=True, timeout=0.05)
#     except queue.Empty:
#         return None

# def put_audio_frame(data):
#     """放入播放数据 (来自服务器)"""
#     try:
#         play_queue.put(data, block=False)
#     except queue.Full:
#         pass # 播放队列满，丢弃旧帧或新帧以追赶实时性
# src/ascend_voice_stream.py
# src/ascend_voice_stream.py
# import pyaudio
# import threading
# import queue
# import time

# # --- 适配 USB 硬件的音频参数 ---
# AUDIO_RATE = 48000
# AUDIO_CHANNELS = 1
# AUDIO_FORMAT = pyaudio.paInt16
# AUDIO_SAMPLES_PER_FRAME = 960 # 20ms at 48k

# record_queue = queue.Queue(maxsize=100)
# play_queue = queue.Queue(maxsize=100)

# _pyaudio = None
# _in_stream = None
# _out_stream = None
# _stop_event = threading.Event()

# def _record_cb(in_data, frame_count, time_info, status):
#     if not _stop_event.is_set():
#         try: record_queue.put(in_data, block=False)
#         except: pass
#     return (None, pyaudio.paContinue)

# def _play_cb(in_data, frame_count, time_info, status):
#     data = b'\x00' * (frame_count * 2)
#     if not _stop_event.is_set():
#         try:
#             if not play_queue.empty():
#                 data = play_queue.get(block=False)
#                 # 简单长度匹配
#                 if len(data) != len(in_data):
#                     data = data.ljust(len(in_data), b'\x00')[:len(in_data)]
#         except: pass
#     return (data, pyaudio.paContinue)

# def start_audio_service():
#     global _pyaudio, _in_stream, _out_stream
#     print("🎤 [Hardware] 启动音频驱动...")
#     try:
#         _pyaudio = pyaudio.PyAudio()
#         # 寻找设备
#         in_idx, out_idx = None, None
#         for i in range(_pyaudio.get_device_count()):
#             info = _pyaudio.get_device_info_by_index(i)
#             if "USB" in info['name']:
#                 if info['maxInputChannels'] > 0: in_idx = i
#                 if info['maxOutputChannels'] > 0: out_idx = i
        
#         print(f"🎤 使用设备索引: In={in_idx}, Out={out_idx}")

#         _in_stream = _pyaudio.open(
#             format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, input=True,
#             input_device_index=in_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_record_cb
#         )
#         _out_stream = _pyaudio.open(
#             format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, output=True,
#             output_device_index=out_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_play_cb
#         )
#         _in_stream.start_stream()
#         _out_stream.start_stream()
#         _stop_event.wait()
#     except Exception as e:
#         print(f"❌ 音频启动失败: {e}")
#     finally:
#         if _in_stream: _in_stream.close()
#         if _out_stream: _out_stream.close()
#         if _pyaudio: _pyaudio.terminate()

# def get_audio_frame():
#     try: return record_queue.get(block=True, timeout=0.01)
#     except: return None

# def put_audio_frame(data):
#     try: play_queue.put(data, block=False)
#     except: pass
# src/ascend_voice_stream.py
# # src/ascend_voice_stream.py
# import pyaudio
# import threading
# import queue
# import time

# # --- 音频参数 (48k) ---
# AUDIO_RATE = 48000
# AUDIO_CHANNELS = 1
# AUDIO_FORMAT = pyaudio.paInt16
# AUDIO_SAMPLES_PER_FRAME = 960 # 20ms

# # 录音队列 (板子 -> PC)
# record_queue = queue.Queue(maxsize=100)

# # 播放缓冲区 (PC -> 板子)
# play_buffer = bytearray()
# buffer_lock = threading.Lock()

# _pyaudio = None
# _in_stream = None
# _out_stream = None
# _stop_event = threading.Event()

# def _record_cb(in_data, frame_count, time_info, status):
#     """录音回调"""
#     if not _stop_event.is_set():
#         try:
#             # 放入队列供 WebSocket 发送
#             record_queue.put(in_data, block=False)
#         except:
#             pass # 队列满则丢弃
#     return (None, pyaudio.paContinue)

# def _play_cb(in_data, frame_count, time_info, status):
#     """播放回调"""
#     bytes_needed = frame_count * 2
#     data = b'\x00' * bytes_needed
    
#     if not _stop_event.is_set():
#         with buffer_lock:
#             if len(play_buffer) >= bytes_needed:
#                 data = bytes(play_buffer[:bytes_needed])
#                 del play_buffer[:bytes_needed]
#             elif len(play_buffer) > 0:
#                 part = bytes(play_buffer)
#                 data = part + b'\x00' * (bytes_needed - len(part))
#                 del play_buffer[:]
            
#     return (data, pyaudio.paContinue)

# def start_audio_service():
#     global _pyaudio, _in_stream, _out_stream
#     print("🎤 [Hardware] 正在智能扫描音频设备...")
#     try:
#         _pyaudio = pyaudio.PyAudio()
        
#         # --- 智能设备选择逻辑 ---
#         cnt = _pyaudio.get_device_count()
#         best_in_idx = None
#         best_out_idx = None
#         max_in_score = -100
#         max_out_score = -100

#         print(f"   共发现 {cnt} 个设备:")
#         for i in range(cnt):
#             info = _pyaudio.get_device_info_by_index(i)
#             name = info.get('name', '')
#             in_ch = info.get('maxInputChannels', 0)
#             out_ch = info.get('maxOutputChannels', 0)
            
#             # 简单的打分机制
#             score = 0
#             if "USB" in name: score += 10       # 优先 USB
#             if "Audio" in name: score += 5      # 优先专用音频设备
#             if "Camera" in name: score -= 20    # ❌ 尽量不选摄像头麦克风
#             if "Web" in name: score -= 10       # ❌ 尽量不选 Web 设别
            
#             print(f"   - [ID {i}] {name} (In:{in_ch} Out:{out_ch}) Score:{score}")

#             # 选择最佳输入
#             if in_ch > 0 and score > max_in_score:
#                 max_in_score = score
#                 best_in_idx = i
            
#             # 选择最佳输出
#             if out_ch > 0 and score > max_out_score:
#                 max_out_score = score
#                 best_out_idx = i
        
#         # 兜底：如果没找到，用默认的
#         if best_in_idx is None: 
#             best_in_idx = _pyaudio.get_default_input_device_info()['index']
#         if best_out_idx is None: 
#             best_out_idx = _pyaudio.get_default_output_device_info()['index']

#         # 获取最终选定的设备名称
#         in_name = _pyaudio.get_device_info_by_index(best_in_idx)['name']
#         out_name = _pyaudio.get_device_info_by_index(best_out_idx)['name']
        
#         print(f"✅ 最终选择:\n   🎤 录音: [ID {best_in_idx}] {in_name}\n   📢 播放: [ID {best_out_idx}] {out_name}")

#         # 启动录音
#         _in_stream = _pyaudio.open(
#             format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, input=True,
#             input_device_index=best_in_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_record_cb
#         )
        
#         # 启动播放
#         _out_stream = _pyaudio.open(
#             format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, output=True,
#             output_device_index=best_out_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_play_cb
#         )
        
#         _in_stream.start_stream()
#         _out_stream.start_stream()
        
#         _stop_event.wait()

#     except Exception as e:
#         print(f"❌ 音频启动失败: {e}")
#     finally:
#         stop_audio_service()

# def stop_audio_service():
#     global _pyaudio, _in_stream, _out_stream
#     _stop_event.set()
#     if _in_stream: 
#         _in_stream.stop_stream()
#         _in_stream.close()
#     if _out_stream: 
#         _out_stream.stop_stream()
#         _out_stream.close()
#     if _pyaudio: 
#         _pyaudio.terminate()

# def get_audio_frame():
#     try:
#         # 获取录音数据 (非阻塞或带超时)
#         return record_queue.get(block=True, timeout=0.01)
#     except:
#         return None

# def put_audio_frame(data):
#     # 存入播放缓冲区
#     with buffer_lock:
#         play_buffer.extend(data)
#         if len(play_buffer) > 48000 * 2: # 防堆积
#             del play_buffer[:-48000]
# src/ascend_voice_stream.py
# # src/ascend_voice_stream.py
# import pyaudio
# import threading
# import queue
# import time

# # --- 适配 USB 硬件的音频参数 ---
# AUDIO_RATE = 48000
# AUDIO_CHANNELS = 1
# AUDIO_FORMAT = pyaudio.paInt16
# AUDIO_SAMPLES_PER_FRAME = 960 # 20ms at 48k

# record_queue = queue.Queue(maxsize=100)
# play_queue = queue.Queue(maxsize=100)

# _pyaudio = None
# _in_stream = None
# _out_stream = None
# _stop_event = threading.Event()

# def _record_cb(in_data, frame_count, time_info, status):
#     if not _stop_event.is_set():
#         try: record_queue.put(in_data, block=False)
#         except: pass
#     return (None, pyaudio.paContinue)

# def _play_cb(in_data, frame_count, time_info, status):
#     data = b'\x00' * (frame_count * 2)
#     if not _stop_event.is_set():
#         try:
#             if not play_queue.empty():
#                 data = play_queue.get(block=False)
#                 # 简单长度匹配
#                 if len(data) != len(in_data):
#                     data = data.ljust(len(in_data), b'\x00')[:len(in_data)]
#         except: pass
#     return (data, pyaudio.paContinue)

# def start_audio_service():
#     global _pyaudio, _in_stream, _out_stream
#     print("🎤 [Hardware] 启动音频驱动...")
#     try:
#         _pyaudio = pyaudio.PyAudio()
#         # 寻找设备
#         in_idx, out_idx = None, None
#         for i in range(_pyaudio.get_device_count()):
#             info = _pyaudio.get_device_info_by_index(i)
#             if "USB" in info['name']:
#                 if info['maxInputChannels'] > 0: in_idx = i
#                 if info['maxOutputChannels'] > 0: out_idx = i
        
#         print(f"🎤 使用设备索引: In={in_idx}, Out={out_idx}")

#         _in_stream = _pyaudio.open(
#             format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, input=True,
#             input_device_index=in_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_record_cb
#         )
#         _out_stream = _pyaudio.open(
#             format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, output=True,
#             output_device_index=out_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
#             stream_callback=_play_cb
#         )
#         _in_stream.start_stream()
#         _out_stream.start_stream()
#         _stop_event.wait()
#     except Exception as e:
#         print(f"❌ 音频启动失败: {e}")
#     finally:
#         if _in_stream: _in_stream.close()
#         if _out_stream: _out_stream.close()
#         if _pyaudio: _pyaudio.terminate()

# def get_audio_frame():
#     try: return record_queue.get(block=True, timeout=0.01)
#     except: return None

# def put_audio_frame(data):
#     try: play_queue.put(data, block=False)
#     except: pass
import pyaudio
import threading
import queue
import time
from ctypes import *
from contextlib import contextmanager

# --- 屏蔽 ALSA 底层烦人的错误日志 ---
ERROR_HANDLER_FUNC = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_int, c_char_p)
def py_error_handler(filename, line, function, err, fmt):
    pass
c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)

@contextmanager
def no_alsa_error():
    asound = cdll.LoadLibrary('libasound.so')
    asound.snd_lib_error_set_handler(c_error_handler)
    yield
    asound.snd_lib_error_set_handler(None)
# -----------------------------------

# --- 音频参数 ---
AUDIO_RATE = 48000
AUDIO_CHANNELS = 1
AUDIO_FORMAT = pyaudio.paInt16
AUDIO_SAMPLES_PER_FRAME = 960 

record_queue = queue.Queue(maxsize=200)
play_buffer = bytearray()
play_lock = threading.Lock()

_pyaudio = None
_in_stream = None
_out_stream = None
_stop_event = threading.Event()

def _record_cb(in_data, frame_count, time_info, status):
    if not _stop_event.is_set():
        try: record_queue.put(in_data, block=False)
        except: pass
    return (None, pyaudio.paContinue)

def _play_cb(in_data, frame_count, time_info, status):
    bytes_needed = frame_count * 2
    data = b'\x00' * bytes_needed
    if not _stop_event.is_set():
        with play_lock:
            if len(play_buffer) >= bytes_needed:
                data = bytes(play_buffer[:bytes_needed])
                del play_buffer[:bytes_needed]
            elif len(play_buffer) > 0:
                part = bytes(play_buffer)
                data = part + b'\x00' * (bytes_needed - len(part))
                del play_buffer[:]
    return (data, pyaudio.paContinue)

def start_audio_service():
    global _pyaudio, _in_stream, _out_stream
    print("🎤 [Hardware] 初始化音频系统...")
    
    # 使用上下文管理器屏蔽 ALSA 错误
    with no_alsa_error():
        try:
            _pyaudio = pyaudio.PyAudio()
            
            # 简化版设备选择逻辑，避免过多日志
            dev_count = _pyaudio.get_device_count()
            in_idx = _pyaudio.get_default_input_device_info()['index']
            out_idx = _pyaudio.get_default_output_device_info()['index']

            found_usb = False
            for i in range(dev_count):
                try:
                    info = _pyaudio.get_device_info_by_index(i)
                    name = info.get('name', '')
                    # 优先找 USB 音频
                    if "USB" in name:
                        if info['maxInputChannels'] > 0: in_idx = i
                        if info['maxOutputChannels'] > 0: out_idx = i
                        found_usb = True
                except: continue
            
            # 如果没找到 USB 且默认设备不可用，尝试硬编码
            if not found_usb:
                # 针对你的日志中的设备情况 (Web Camera 和 AB13X)
                # 你的日志显示: Device 2 is USB Input (hw:2,0)
                # Device 1 is AB13X Output (hw:1,0)
                pass 

            print(f"✅ 选定音频设备 -> 录音ID: {in_idx} | 播放ID: {out_idx}")

            _in_stream = _pyaudio.open(
                format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, input=True,
                input_device_index=in_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
                stream_callback=_record_cb
            )
            
            _out_stream = _pyaudio.open(
                format=AUDIO_FORMAT, channels=AUDIO_CHANNELS, rate=AUDIO_RATE, output=True,
                output_device_index=out_idx, frames_per_buffer=AUDIO_SAMPLES_PER_FRAME,
                stream_callback=_play_cb
            )
            
            _in_stream.start_stream()
            _out_stream.start_stream()
            print("🎤 音频服务启动成功")
            
            _stop_event.wait()

        except Exception as e:
            print(f"❌ 音频启动异常: {e}")
        finally:
            stop_audio_service()

def stop_audio_service():
    global _pyaudio, _in_stream, _out_stream
    _stop_event.set()
    try:
        if _in_stream: _in_stream.close()
        if _out_stream: _out_stream.close()
        if _pyaudio: _pyaudio.terminate()
    except: pass

def get_audio_frame():
    try: return record_queue.get(block=True, timeout=0.005) # 减少超时时间防止阻塞事件循环
    except: return None

def put_audio_frame(data):
    if not data: return
    with play_lock:
        play_buffer.extend(data)
        if len(play_buffer) > 48000 * 2: 
            del play_buffer[0 : 48000]