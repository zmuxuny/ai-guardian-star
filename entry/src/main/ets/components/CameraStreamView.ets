import webview from '@ohos.web.webview';
import { VIDEO_FEED_URL } from '../config';

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

  aboutToAppear(): void { this.disposed = false; this.scheduleFit(); }
  aboutToDisappear(): void {
    this.disposed = true;
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = -1;
  }

  private scheduleFit(): void {
    if (this.disposed) return;
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = setTimeout((): void => { this.timer = -1; this.fit(); }, 250);
  }

  private fit(): void {
    if (this.disposed || this.ready) return;
    if (this.attempts++ >= 40) { this.unavailable = true; return; }
    const version = this.streamVersion;
    const fit = this.fullscreen ? 'contain' : 'cover';
    const script = `(() => {
      const image = document.querySelector('img');
      if (!image || image.naturalWidth === 0) return 'waiting';
      document.documentElement.style.cssText = 'margin:0;width:100%;height:100%;overflow:hidden;background:#0f172a';
      document.body.style.cssText = 'margin:0;width:100vw;height:100vh;overflow:hidden;background:#0f172a';
      image.style.cssText = 'display:block;width:100vw;height:100vh;max-width:none;max-height:none;margin:0;object-fit:${fit}';
      return 'ready';
    })()`;
    this.controller.runJavaScript(script).then((result: string): void => {
      if (this.disposed || version !== this.streamVersion) return;
      // Web engines may serialize JavaScript string results as JSON strings.
      if (result === 'ready' || result === '"ready"') { this.ready = true; this.unavailable = false; }
      else this.scheduleFit();
    }).catch((): void => {
      if (!this.disposed && version === this.streamVersion) this.scheduleFit();
    });
  }

  private retry(): void {
    if (this.timer !== -1) clearTimeout(this.timer);
    this.timer = -1;
    this.ready = false;
    this.unavailable = false;
    this.attempts = 0;
    this.streamVersion++;
    this.scheduleFit();
  }

  build() {
    Stack() {
      ForEach([this.streamVersion], (version: number) => {
        Web({ src: VIDEO_FEED_URL, controller: this.controller })
          .width('100%').height('100%')
          .onPageBegin((): void => { this.scheduleFit(); })
      }, (version: number): string => `${version}`)
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
        }.width('100%').height('100%').justifyContent(FlexAlign.Center)
          .backgroundColor('#0f172a')
      }
    }.width('100%').height('100%').backgroundColor('#0f172a')
  }
}
