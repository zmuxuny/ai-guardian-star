import { MqttManager } from './MqttManager';
import { CarePalette, carePalette } from '../common/CarePalette';
import { CameraStreamView } from '../components/CameraStreamView';
import { ThemeManager } from '../common/ThemeManager';

@Builder
export function CameraFullscreenBuilder(): void { CameraFullscreen(); }

@Component
struct CameraFullscreen {
  @StorageLink('homeCameraFullscreenActive') fullscreenActive: boolean = false;
  @State mqtt: MqttManager = MqttManager.getInstance();

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  private pathStack: NavPathStack = new NavPathStack();

  aboutToAppear(): void { this.fullscreenActive = true; }
  aboutToDisappear(): void { this.fullscreenActive = false; }

  build() {
    NavDestination() {
      Stack({ alignContent: Alignment.TopStart }) {
        CameraStreamView({ fullscreen: true, placeholderSurface: this.palette().backdrop })
        Button({ type: ButtonType.Normal }) {
          Row({ space: 8 }) {
            Image($r('app.media.ic_camera_back')).width(20).height(20)
            Text('返回').fontSize(15).fontColor('#ffffff')
          }
        }.height(44).padding({ left: 14, right: 16 }).borderRadius(22)
          .backgroundColor(this.palette().solid).margin({ left: 16, top: 16 })
          .accessibilityText('退出摄像头全屏查看')
          .onClick((): void => { this.pathStack.pop(); })
      }.width('100%').height('100%').backgroundColor(this.palette().backdrop)
    }.hideTitleBar(true).backgroundColor(this.palette().backdrop)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      .onReady((context: NavDestinationContext): void => { this.pathStack = context.pathStack; })
      .onShown((): void => { ThemeManager.getInstance().updateSystemUI(true); })
  }
}
