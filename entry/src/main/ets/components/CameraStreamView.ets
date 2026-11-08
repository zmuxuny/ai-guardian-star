import { image } from '@kit.ImageKit';
import { ECS_BASE_URL } from '../config';
import { CameraFrameClient } from '../common/CameraFrameClient';

/** Native latest-frame preview; no Web surface or Blob image lifecycle. */
@Component
export struct CameraStreamView {
  @Prop fullscreen: boolean = false;
  @State frame?: image.PixelMap = undefined;
  @State ready: boolean = false;
  @State unavailable: boolean = false;
  private client: CameraFrameClient = new CameraFrameClient();
  private timer: number = -1;
  private generation: number = 0;
  private disposed: boolean = true;
  private visible: boolean = true;
  private sequence: string = '';
  private retired: image.PixelMap[] = [];
  private startedAt: number = 0;
  private statsAt: number = 0;
  private frames: number = 0;
  private requestMs: number = 0;
  private decodeMs: number = 0;
  private lastFrameAt: number = 0;
  private failures: number = 0;

  aboutToAppear(): void {
    this.disposed = false;
    this.failures = 0;
    this.startedAt = Date.now();
    this.statsAt = Date.now();
    this.schedule(0);
  }

  aboutToDisappear(): void {
    this.disposed = true;
    this.suspend();
    if (this.frame !== undefined) this.retired.push(this.frame);
    this.frame = undefined;
    for (const pixels of this.retired) pixels.release();
    this.retired = [];
  }

  private suspend(): void {
    this.generation++;
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = -1;
    this.client.cancel();
  }

  private schedule(delay: number): void {
    if (this.disposed || !this.visible) return;
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = setTimeout((): void => { this.timer = -1; this.loadFrame(); }, delay);
  }

  private async loadFrame(): Promise<void> {
    if (this.disposed || !this.visible) return;
    const version = this.generation;
    const started = Date.now();
    let delay = 0;
    try {
      const path = this.fullscreen ? '/video_preview_full' : '/video_preview';
      const result = await this.client.fetch(`${ECS_BASE_URL}${path}?t=${started}`, this.sequence);
      if (this.disposed || version !== this.generation) {
        if (result !== undefined) await result.pixels.release();
        return;
      }
      this.failures = 0;
      if (result !== undefined) {
        this.lastFrameAt = Date.now();
        this.sequence = result.sequence;
        if (this.frame !== undefined) this.retired.push(this.frame);
        this.frame = result.pixels;
        // Retain two previous bitmaps until ArkUI has attached the new image.
        if (this.retired.length > 2) await this.retired.shift()?.release();
        this.unavailable = false;
        this.frames++;
        this.requestMs += result.requestMs;
        this.decodeMs += result.decodeMs;
        const elapsed = Date.now() - this.statsAt;
        if (elapsed >= 5000) {
          console.info(`[CameraPreviewNative] fps=${(this.frames * 1000 / elapsed).toFixed(1)}, ` +
            `requestMs=${Math.round(this.requestMs / this.frames)}, decodeMs=${Math.round(this.decodeMs / this.frames)}`);
          this.statsAt = Date.now(); this.frames = 0; this.requestMs = 0; this.decodeMs = 0;
        }
      }
      this.checkFreshness();
      delay = Math.max(0, 67 - (Date.now() - started));
    } catch (_error) {
      if (version !== this.generation || this.disposed) return;
      this.checkFreshness();
      this.failures = Math.min(this.failures + 1, 4);
      delay = Math.min(1500, 200 * Math.pow(2, this.failures - 1));
    }
    if (version === this.generation) this.schedule(delay);
  }

  private checkFreshness(): void {
    const last = this.frame !== undefined ? this.lastFrameAt : this.startedAt;
    const tolerance = this.frame !== undefined ? 2000 : 10000;
    if (Date.now() - last >= tolerance) this.unavailable = true;
  }

  private retry(): void {
    this.suspend();
    this.failures = 0;
    this.sequence = '';
    this.unavailable = false;
    this.startedAt = Date.now();
    this.schedule(0);
  }

  build() {
    Stack({ alignContent: Alignment.Center }) {
      if (this.frame !== undefined) {
        Image(this.frame)
          .width('100%').height('100%')
          .objectFit(this.fullscreen ? ImageFit.Contain : ImageFit.Cover)
          .onComplete((): void => { this.ready = true; })
          .onError((): void => { this.unavailable = true; })
      }
      if (!this.ready) {
        Column({ space: 8 }) {
          if (this.unavailable) {
            Image($r('app.media.ic_camera_off')).width(30).height(30)
            Text('暂时无法获取画面').fontSize(12).fontColor('#cbd5e1')
            if (this.fullscreen) {
              Button('重新连接').height(44).fontSize(14).backgroundColor('#2563eb')
                .onClick((): void => { this.retry(); })
            }
          } else {
            LoadingProgress().width(24).height(24).color('#93c5fd')
            Text('正在连接摄像头').fontSize(12).fontColor('#cbd5e1')
          }
        }.width('100%').height('100%').justifyContent(FlexAlign.Center).backgroundColor('#0f172a')
      } else if (this.unavailable) {
        Text('画面中断，正在重连…').fontSize(12).fontColor('#cbd5e1')
          .padding(8).backgroundColor('#cc0f172a').align(Alignment.Bottom)
      }
    }.width('100%').height('100%').backgroundColor('#0f172a')
      .onVisibleAreaChange([0, 1], (isVisible: boolean): void => {
        if (this.visible === isVisible) return;
        this.visible = isVisible;
        if (isVisible) this.schedule(0); else this.suspend();
      })
  }
}
