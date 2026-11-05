import webview from '@ohos.web.webview';
import { ECS_BASE_URL } from '../config';
import { buildMjpegPage } from './MjpegPage';

/** One live MJPEG view; the fullscreen page replaces the preview connection. */
@Component
export struct CameraStreamView {
  @Prop fullscreen: boolean = false;
  @State ready: boolean = false;
  @State unavailable: boolean = false;
  @State streamVersion: number = 0;
  private controller: webview.WebviewController = new webview.WebviewController();
  private timer: number = -1;
  private attempts: number = 0;
  private disposed: boolean = false;

  aboutToAppear(): void { this.disposed = false; this.schedulePoll(); }
  aboutToDisappear(): void {
    this.disposed = true;
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = -1;
  }

  private loadPage(): void {
    // baseUrl 设为云端地址，页面与视频同源，页面内 fetch 才能读取流。
    const html = buildMjpegPage('/video_feed', this.fullscreen ? 'contain' : 'cover');
    try {
      this.controller.loadData(html, 'text/html', 'UTF-8', `${ECS_BASE_URL}/`, `${ECS_BASE_URL}/`);
    } catch (e) {
      console.error(`CameraStreamView loadData failed: ${JSON.stringify(e)}`);
    }
  }

  private schedulePoll(): void {
    if (this.disposed) return;
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = setTimeout((): void => { this.timer = -1; this.poll(); }, 500);
  }

  // 只等第一帧；之后的断流由页面自己重连并提示。
  private poll(): void {
    if (this.disposed || this.ready) return;
    // 约 10 秒还没画面就提示，但页面仍在后台重连，出画面后自动切回。
    if (this.attempts++ >= 20) this.unavailable = true;
    const version = this.streamVersion;
    this.controller.runJavaScript('document.body ? document.body.dataset.state : ""').then((result: string): void => {
      if (this.disposed || version !== this.streamVersion) return;
      // Web engines may serialize JavaScript string results as JSON strings.
      if (result === 'live' || result === '"live"') { this.ready = true; this.unavailable = false; }
      else this.schedulePoll();
    }).catch((): void => {
      if (!this.disposed && version === this.streamVersion) this.schedulePoll();
    });
  }

  private retry(): void {
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = -1;
    this.ready = false;
    this.unavailable = false;
    this.attempts = 0;
    this.streamVersion++;
    this.schedulePoll();
  }

  build() {
    Stack() {
      ForEach([this.streamVersion], (version: number) => {
        Web({ src: 'about:blank', controller: this.controller })
          .width('100%').height('100%')
          .backgroundColor('#0f172a')
          // 等 about:blank 加载完再换成画面页；在 onControllerAttached 里加载会被初始导航中止（ERR_ABORTED）。
          .onPageEnd((event: OnPageEndEvent): void => {
            if (event.url === 'about:blank') this.loadPage();
          })
      }, (version: number): string => `${version}`)
      if (!this.ready) {
        Column({ space: 8 }) {
          if (this.unavailable) {
            Image($r('app.media.ic_camera_off')).width(30).height(30)
            Text('暂时无法获取画面').fontSize(12).fontColor('#cbd5e1')
            // 首页小预览上面盖着"点按全屏"的点击层，按钮只放在全屏页。
            if (this.fullscreen) {
              Button('重新连接').height(44).fontSize(14).backgroundColor('#2563eb')
                .onClick((): void => { this.retry(); })
            }
          } else {
            LoadingProgress().width(24).height(24).color('#93c5fd')
            Text('正在连接摄像头').fontSize(12).fontColor('#cbd5e1')
          }
        }.width('100%').height('100%').justifyContent(FlexAlign.Center)
          .backgroundColor('#0f172a')
      }
    }.width('100%').height('100%').backgroundColor('#0f172a')
  }
}
