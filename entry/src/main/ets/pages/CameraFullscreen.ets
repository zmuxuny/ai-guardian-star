import { CameraStreamView } from '../components/CameraStreamView';
import { ThemeManager } from '../common/ThemeManager';
import { window } from '@kit.ArkUI';
import { common } from '@kit.AbilityKit';

@Builder
export function CameraFullscreenBuilder(): void { CameraFullscreen(); }

@Component
struct CameraFullscreen {
  @StorageLink('homeCameraFullscreenActive') fullscreenActive: boolean = false;
  private pathStack: NavPathStack = new NavPathStack();

  aboutToAppear(): void { this.fullscreenActive = true; }
  aboutToDisappear(): void { this.fullscreenActive = false; }

  private async setSystemText(fullscreen: boolean): Promise<void> {
    try {
      const context = this.getUIContext().getHostContext() as common.UIAbilityContext;
      const win = await window.getLastWindow(context);
      await win.setWindowSystemBarProperties({
        statusBarContentColor: fullscreen || ThemeManager.getInstance().isDarkMode ? '#ffffff' : '#000000',
        navigationBarContentColor: fullscreen || ThemeManager.getInstance().isDarkMode ? '#ffffff' : '#000000'
      });
    } catch (_error) {}
  }

  build() {
    NavDestination() {
      Stack({ alignContent: Alignment.TopStart }) {
        CameraStreamView({ fullscreen: true })
        Button({ type: ButtonType.Normal }) {
          Row({ space: 8 }) {
            Image($r('app.media.ic_camera_back')).width(20).height(20)
            Text('返回').fontSize(15).fontColor('#ffffff')
          }
        }.height(44).padding({ left: 14, right: 16 }).borderRadius(22)
          .backgroundColor('#cc1e293b').margin({ left: 16, top: 16 })
          .accessibilityText('退出摄像头全屏查看')
          .onClick((): void => { this.pathStack.pop(); })
      }.width('100%').height('100%').backgroundColor('#0f172a')
    }.hideTitleBar(true).backgroundColor('#0f172a')
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      .onReady((context: NavDestinationContext): void => { this.pathStack = context.pathStack; })
      .onShown((): void => { this.setSystemText(true); })
      .onHidden((): void => { this.setSystemText(false); })
  }
}
