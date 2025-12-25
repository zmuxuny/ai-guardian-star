import audio from '@ohos.multimedia.audio';
import webSocket from '@ohos.net.webSocket';
import util from '@ohos.util'; // 引入工具库用于 Base64 编码
import { BusinessError } from '@ohos.base';

export class AudioTransferManager {
  private static instance: AudioTransferManager;

  // 鲲鹏板子的 Socket.IO 地址
  private readonly WS_URL = 'ws://192.168.5.118:5000/socket.io/?EIO=4&transport=websocket';

  // 采样率 48000
  private readonly SAMPLE_RATE = audio.AudioSamplingRate.SAMPLE_RATE_48000;

  private ws: webSocket.WebSocket | undefined = undefined;
  private audioCapturer: audio.AudioCapturer | undefined = undefined;
  private audioRenderer: audio.AudioRenderer | undefined = undefined;
  private isConnected: boolean = false;

  // Base64 工具实例
  private base64Helper = new util.Base64Helper();

  public static getInstance(): AudioTransferManager {
    if (!AudioTransferManager.instance) {
      AudioTransferManager.instance = new AudioTransferManager();
    }
    return AudioTransferManager.instance;
  }

  async startCall(): Promise<void> {
    if (this.isConnected) return;

    try {
      this.ws = webSocket.createWebSocket();

      this.ws.on('open', (err, value) => {
        console.info('Socket.IO 连接成功');
        this.isConnected = true;
        // 1. 发送握手
        this.ws?.send("40"); // 加上 ? 避免报错
        this.startAudioDevices();
      });

      this.ws.on('message', async (err, value) => {
        if (!err && value) {
          // 2. 处理心跳
          if (typeof value === 'string') {
            if (value === "2") {
              this.ws?.send("3");
              return;
            }
          }

          // 3. 处理接收到的音频 (解决声音小的问题)
          if (value instanceof ArrayBuffer && this.audioRenderer && this.audioRenderer.state === audio.AudioState.STATE_RUNNING) {
            // 放大 3 倍音量
            const amplifiedData = this.amplifyAudio(value, 3.0);
            await this.audioRenderer.write(amplifiedData);
          }
        }
      });

      this.ws.on('error', (err) => {
        console.error('Socket 错误:', JSON.stringify(err));
      });

      await this.ws.connect(this.WS_URL);

    } catch (error) {
      console.error('启动失败:', JSON.stringify(error));
      this.stopCall();
    }
  }

  // 初始化音频并发送 Base64
  private async startAudioDevices() {
    try {
      // 初始化播放器
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

      // 初始化录音器
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

      // 录音数据处理
      this.audioCapturer.on('readData', (buffer: ArrayBuffer) => {
        // 🔥 这里也加上检查，确保 ws 存在 🔥
        if (this.isConnected && this.ws) {
          try {
            // 1. 转 Uint8Array
            let u8Arr = new Uint8Array(buffer);

            // 2. 转 Base64
            let base64Str = this.base64Helper.encodeToStringSync(u8Arr);

            // 3. 拼接 Socket.IO 格式
            let socketIoMessage = `42["audio_from_pc","${base64Str}"]`;

            // 4. 发送 (加上 ? 防止报错)
            this.ws?.send(socketIoMessage);

          } catch (e) {
            console.error("发送音频错误", JSON.stringify(e));
          }
        }
      });

      await this.audioCapturer.start();

    } catch (e) {
      console.error('音频设备初始化失败:', JSON.stringify(e));
    }
  }

  // 数字音量放大
  private amplifyAudio(buffer: ArrayBuffer, gain: number): ArrayBuffer {
    let int16Array = new Int16Array(buffer);
    for (let i = 0; i < int16Array.length; i++) {
      let val = int16Array[i] * gain;
      // 防止溢出
      if (val > 32767) val = 32767;
      if (val < -32768) val = -32768;
      int16Array[i] = val;
    }
    return int16Array.buffer as ArrayBuffer;
  }

  async stopCall(): Promise<void> {
    this.isConnected = false;

    if (this.audioCapturer) {
      await this.audioCapturer.stop();
      await this.audioCapturer.release();
      this.audioCapturer = undefined;
    }

    if (this.audioRenderer) {
      await this.audioRenderer.stop();
      await this.audioRenderer.release();
      this.audioRenderer = undefined;
    }

    if (this.ws) {
      this.ws.off('open');
      this.ws.off('message');
      this.ws.off('error');
      // 加上 ? 防止报错
      await this.ws?.close();
      this.ws = undefined;
    }
  }
}