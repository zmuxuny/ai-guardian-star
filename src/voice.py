import wave
import sys
import os

# 1. 定义你的 .wav 文件路径
WAVE_FILE_PATH = "/root/yolo/output.wav"

def test_wav_file(file_path):
    """
    打开、读取并显示WAV文件的信息。
    """
    
    # 2. 检查文件是否存在
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        print("请确保文件路径拼写正确，并且文件确实存在于该位置。")
        return

    try:
        # 3. 打开 .wav 文件
        # 'rb' 表示 'read binary' (二进制读取模式)
        with wave.open(file_path, 'rb') as wf:
            
            # 4. 读取并打印WAV文件的参数
            print(f"成功打开文件: {file_path}")
            print("---------------------------------")
            print(f"  通道数 (Channels): {wf.getnchannels()}")
            print(f"  采样宽度 (Sample Width): {wf.getsampwidth()} 字节")
            print(f"  采样率 (Rate): {wf.getframerate()} Hz")
            print(f"  总帧数 (Frames): {wf.getnframes()}")
            
            duration = wf.getnframes() / float(wf.getframerate())
            print(f"  音频时长 (Duration): {duration:.2f} 秒")
            print("---------------------------------")

            # 5. 读取完整的音频数据
            # wf.getnframes() 返回总帧数
            frames_data = wf.readframes(wf.getnframes())
            
            print(f"成功读取了 {len(frames_data)} 字节的音频数据。")

            # -----------------------------------------------------------
            # 在这里添加你的下一步处理逻辑
            #
            # 例如，你之后可能会把 'frames_data' 传递给
            # 一个语音识别模型或音频处理函数
            # 
            # 示例: process_audio_data(frames_data, wf.getframerate())
            # -----------------------------------------------------------

            print("\n模拟测试完成。")

    except wave.Error as e:
        print(f"错误: 无法读取WAV文件。")
        print(f"文件 {file_path} 可能已损坏或不是一个有效的WAV文件。")
        print(f"详细信息: {e}")
    except Exception as e:
        print(f"发生了意外错误: {e}")

# --- 脚本执行入口 ---
if __name__ == "__main__":
    print("开始执行 'voice.py' 脚本...")
    test_wav_file(WAVE_FILE_PATH)