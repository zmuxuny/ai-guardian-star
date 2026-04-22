import audio from "@ohos.multimedia.audio";
import webSocket from "@ohos.net.webSocket";
import { BusinessError } from "@ohos.base";
import { taskpool } from "@kit.ArkTS";

export class AudioTransferManager {
  private static instance: AudioTransferManager;

  //private readonly WS_URL = 'ws://192.168.137.100:5000/ws/intercom';
  //private readonly WS_URL = 'ws://10.190.205.195:5000/ws/intercom';
  private readonly WS_URL = "ws://117.78.9.144:6000/ws/intercom";

  private ws: webSocket.WebSocket | undefined = undefined;
  private audioCapturer: audio.AudioCapturer | undefined = undefined;
  private audioRenderer: audio.AudioRenderer | undefined = undefined;
  private isConnected: boolean = false;

  // PCM 接收队列，writeData 回调时消费
  private pcmQueue: ArrayBuffer[] = [];
  private readonly MAX_QUEUE: number = 40;

  public static getInstance(): AudioTransferManager {
    if (!AudioTransferManager.instance) {
      AudioTransferManager.instance = new AudioTransferManager();
    }
    return AudioTransferManager.instance;
  }

  async startCall(): Promise<void> {
    if (this.isConnected) return;
    this.pcmQueue = [];

    try {
      // ---- A. 先创建播放器并注册 writeData 回调 ----
      // writeData 是系统按固定节拍主动拉数据的回调，必须在 start() 前注册
      const rendererOptions: audio.AudioRendererOptions = {
        streamInfo: {
          samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_48000,
          channels: audio.AudioChannel.CHANNEL_1,
          sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
          encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW,
        },
        rendererInfo: {
          usage: audio.StreamUsage.STREAM_USAGE_MUSIC,
          rendererFlags: 0,
        },
      };
      this.audioRenderer = await audio.createAudioRenderer(rendererOptions);

      this.audioRenderer.on("stateChange", (state: audio.AudioState) => {
        console.info("[Audio] Renderer state: " + state);
      });

      this.audioRenderer.on("writeData", (buffer: ArrayBuffer) => {
        // 系统每 20ms 来拿一次数据，从队列里取，没有就静音
        const dst = new Uint8Array(buffer);
        if (this.pcmQueue.length > 0) {
          const frame = this.pcmQueue.shift()!;
          const src = new Uint8Array(frame);
          const len = Math.min(dst.byteLength, src.byteLength);
          dst.set(src.subarray(0, len), 0);
          if (len < dst.byteLength) {
            dst.fill(0, len);
          }
        } else {
          dst.fill(0);
        }
      });

      await this.audioRenderer.start();
      console.info("[Audio] 播放器已启动");

      // ---- B. 创建录音器 ----
      const capturerOptions: audio.AudioCapturerOptions = {
        streamInfo: {
          samplingRate: audio.AudioSamplingRate.SAMPLE_RATE_48000,
          channels: audio.AudioChannel.CHANNEL_1,
          sampleFormat: audio.AudioSampleFormat.SAMPLE_FORMAT_S16LE,
          encodingType: audio.AudioEncodingType.ENCODING_TYPE_RAW,
        },
        capturerInfo: {
          source: audio.SourceType.SOURCE_TYPE_MIC,
          capturerFlags: 0,
        },
      };
      this.audioCapturer = await audio.createAudioCapturer(capturerOptions);

      this.audioCapturer.on("stateChange", (state: audio.AudioState) => {
        console.info("[Audio] Capturer state: " + state);
      });

      this.audioCapturer.on("readData", (buffer: ArrayBuffer) => {
        if (this.ws && this.isConnected) {
          this.ws.send(buffer).catch((_e: BusinessError) => {});
        }
      });

      await this.audioCapturer.start();
      console.info("[Audio] 录音器已启动");

      // ---- C. 最后建立 WebSocket 连接 ----
      // 音频设备就绪后再连，避免丢帧
      this.ws = webSocket.createWebSocket();

      this.ws.on("open", (_err, _val) => {
        this.isConnected = true;
        console.info("[Audio] WebSocket 已连接，双向通话就绪");
      });

      this.ws.on("error", (err) => {
        console.error("[Audio] WebSocket 错误:", JSON.stringify(err));
      });

      // 收到板子 PCM → 放入队列
      this.ws.on("message", (_err, value) => {
        console.info(
          "[Audio] 收到消息 typeof=" +
            typeof value +
            " isAB=" +
            (value instanceof ArrayBuffer) +
            " byteLen=" +
            (value instanceof ArrayBuffer ? value.byteLength : (value as string).length),
        );
        try {
          let buf: ArrayBuffer;
          if (value instanceof ArrayBuffer) {
            buf = value;
          } else {
            // 部分鸿蒙版本二进制帧以 string 形式到达，需转换
            const str = value as string;
            const ab = new ArrayBuffer(str.length);
            const view = new Uint8Array(ab);
            for (let i = 0; i < str.length; i++) {
              view[i] = str.charCodeAt(i) & 0xff;
            }
            buf = ab;
          }
          if (buf.byteLength > 0) {
            if (this.pcmQueue.length >= this.MAX_QUEUE) {
              this.pcmQueue.shift();
            }
            this.pcmQueue.push(buf);
          }
        } catch (e) {
          console.error("[Audio] message处理失败:", JSON.stringify(e));
        }
      });

      await this.ws.connect(this.WS_URL);
    } catch (err) {
      console.error("[Audio] 启动失败:", JSON.stringify(err));
      await this.stopCall();
    }
  }

  async stopCall(): Promise<void> {
    this.isConnected = false;
    this.pcmQueue = [];

    if (this.audioCapturer) {
      try {
        await this.audioCapturer.stop();
      } catch (_) {}
      try {
        await this.audioCapturer.release();
      } catch (_) {}
      this.audioCapturer = undefined;
    }

    if (this.audioRenderer) {
      try {
        await this.audioRenderer.stop();
      } catch (_) {}
      try {
        await this.audioRenderer.release();
      } catch (_) {}
      this.audioRenderer = undefined;
    }

    if (this.ws) {
      this.ws.off("open");
      this.ws.off("message");
      this.ws.off("error");
      try {
        await this.ws.close();
      } catch (_) {}
      this.ws = undefined;
    }

    console.info("[Audio] 通话已结束");
  }
}
