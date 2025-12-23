import audio from '@ohos.multimedia.audio';
import webSocket from '@ohos.net.webSocket'; // 引入 WebSocket 模块
import { BusinessError } from '@ohos.base';

export class AudioTransferManager {
  private static instance: AudioTransferManager;

  // === 配置区域 ===
  // 这里填开发板的 IP，端口号跟网页一样用 5000
  private readonly WS_URL = 'ws://192.168.137.100:5000/ws/intercom';
  // private readonly WS_URL = 'ws://192.168.5.118:5000/ws/intercom';

  // 采样率必须与 Python 端一致 (网页端是 48000)
  private readonly SAMPLE_RATE = audio.AudioSamplingRate.SAMPLE_RATE_48000;

  // === 内部变量 ===
  private ws: webSocket.WebSocket | undefined = undefined;
  private audioCapturer: audio.AudioCapturer | undefined = undefined;
  private audioRenderer: audio.AudioRenderer | undefined = undefined;
  private isConnected: boolean = false;

  public static getInstance(): AudioTransferManager {
    if (!AudioTransferManager.instance) {
      AudioTransferManager.instance = new AudioTransferManager();
    }
    return AudioTransferManager.instance;
  }

  // === 1. 开始通话 ===
  async startCall(): Promise<void> {
    if (this.isConnected) return;

    try {
      console.info('正在连接 WebSocket:', this.WS_URL);

      // 1. 创建并连接 WebSocket
      this.ws = webSocket.createWebSocket();

      // 监听打开事件
      this.ws.on('open', (err, value) => {
        console.info('WebSocket 连接成功！开始初始化音频...');
        this.isConnected = true;
        // 连接通了再启动音频，防止丢包
        this.startAudioDevices();
      });

      // 监听错误
      this.ws.on('error', (err) => {
        console.error('WebSocket 错误:', JSON.stringify(err));
      });

      // 监听消息 (收到开发板的声音)
      this.ws.on('message', async (err, value) => {
        if (!err && value) {
          // value 通常是 string 或 ArrayBuffer
          // 如果是 ArrayBuffer，直接写入播放器
          if (value instanceof ArrayBuffer && this.audioRenderer && this.audioRenderer.state === audio.AudioState.STATE_RUNNING) {
            await this.audioRenderer.write(value);
          }
        }
      });

      // 发起连接
      await this.ws.connect(this.WS_URL);

    } catch (error) {
      console.error('启动失败:', JSON.stringify(error));
      this.stopCall(); // 出错就清理
    }
  }

  // === 内部方法：启动音频设备 ===
  private async startAudioDevices() {
    try {
      // --- A. 初始化播放器 (听开发板) ---
      const rendererOptions: audio.AudioRendererOptions = {
        streamInfo: {
          samplingRate: this.SAMPLE_RATE,
          channels: audio.AudioChannel.CHANNEL_1,
          sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
          encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
        },
        rendererInfo: {
          usage: audio.StreamUsage.STREAM_USAGE_VOICE_COMMUNICATION,
          rendererFlags: 0
        }
      };
      this.audioRenderer = await audio.createAudioRenderer(rendererOptions);
      await this.audioRenderer.start();

      // --- B. 初始化录音器 (说给开发板) ---
      const capturerOptions: audio.AudioCapturerOptions = {
        streamInfo: {
          samplingRate: this.SAMPLE_RATE,
          channels: audio.AudioChannel.CHANNEL_1,
          sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
          encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW
        },
        capturerInfo: {
          source: audio.SourceType.SOURCE_TYPE_MIC,
          capturerFlags: 0
        }
      };
      this.audioCapturer = await audio.createAudioCapturer(capturerOptions);

      // 监听录音数据 -> 发送给 WebSocket
      this.audioCapturer.on('readData', (buffer: ArrayBuffer) => {
        if (this.isConnected && this.ws) {
          // 直接发送 ArrayBuffer
          this.ws.send(buffer).catch((e: BusinessError) => {
            // 忽略微小的发送错误
          });
        }
      });

      await this.audioCapturer.start();
      console.info('双向通话已完全启动');

    } catch (e) {
      console.error('音频设备初始化失败:', JSON.stringify(e));
    }
  }

  // === 2. 停止通话 ===
  async stopCall(): Promise<void> {
    this.isConnected = false;

    // 停止录音
    if (this.audioCapturer) {
      await this.audioCapturer.stop();
      await this.audioCapturer.release();
      this.audioCapturer = undefined;
    }

    // 停止播放
    if (this.audioRenderer) {
      await this.audioRenderer.stop();
      await this.audioRenderer.release();
      this.audioRenderer = undefined;
    }

    // 关闭 WebSocket
    if (this.ws) {
      // 移除所有监听器防止内存泄漏
      this.ws.off('open');
      this.ws.off('message');
      this.ws.off('error');

      await this.ws.close();
      this.ws = undefined;
    }

    console.info('通话已结束');
  }
}