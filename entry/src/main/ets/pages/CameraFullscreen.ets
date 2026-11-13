import { MqttManager } from './MqttManager';
import { CarePalette, carePalette, careIconTint } from '../common/CarePalette';
import { CameraStreamView } from '../components/CameraStreamView';
import { ThemeManager } from '../common/ThemeManager';
import { AudioTransferManager } from '../common/AudioTransferManager';
import { toggleDeviceCall } from '../common/CallControl';
import { softTap } from '../common/UiFeedback';

@Builder
export function CameraFullscreenBuilder(): void { CameraFullscreen(); }

@Component
struct CameraFullscreen {
  @StorageLink('homeCameraFullscreenActive') fullscreenActive: boolean = false;
  @State mqtt: MqttManager = MqttManager.getInstance();
  @State isTalking: boolean = false;
  @State callBusy: boolean = false;
  private audio: AudioTransferManager = AudioTransferManager.getInstance();
  private callTimer: number = -1;

  private palette(): CarePalette {
    return carePalette(this.mqtt.isFallDetected, this.mqtt.isSedentaryDetected, this.mqtt.deviceOnline);
  }

  private pathStack: NavPathStack = new NavPathStack();

  aboutToAppear(): void {
    this.fullscreenActive = true;
    this.isTalking = this.audio.isCallActive();
    this.callTimer = setInterval((): void => { this.isTalking = this.audio.isCallActive(); }, 1000) as number;
  }

  aboutToDisappear(): void {
    this.fullscreenActive = false;
    if (this.callTimer !== -1) clearInterval(this.callTimer);
    this.callTimer = -1;
  }

  // 返回首页不算离开，通话继续；首页销毁时才由首页挂断
  private async toggleCall(): Promise<void> {
    if (this.callBusy) return;
    this.callBusy = true;
    try {
      await toggleDeviceCall(this.getUIContext(), (): boolean => true);
    } finally {
      this.callBusy = false;
      this.isTalking = this.audio.isCallActive();
    }
  }

  private callLabel(): string {
    if (this.callBusy) return this.isTalking ? '结束中' : '连接中';
    return this.isTalking ? '挂断' : '通话';
  }

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

        // 底部通话按钮：看画面时可直接喊话
        Button({ type: ButtonType.Capsule }) {
          Row({ space: 8 }) {
            Image(this.isTalking ? $r('app.media.ic_call_end') : $r('app.media.ic_phone'))
              .width(20).height(20).supportSvg2(true)
              .colorFilter(careIconTint(this.isTalking ? '#FFFFFF' : this.palette().solid))
            Text(this.callLabel()).fontSize(17).fontWeight(FontWeight.Medium)
              .fontColor(this.isTalking ? '#FFFFFF' : this.palette().solid)
          }
        }
        .width(180).height(54).stateEffect(true)
        .backgroundColor(this.isTalking ? '#C7361F' : '#FFFFFF')
        .shadow({ radius: 26, offsetY: 14, color: '#80000000' })
        .enabled(!this.callBusy)
        .position({ left: '50%', bottom: 48 }).translate({ x: -90 })
        .accessibilityText(this.isTalking ? '挂断通话' : '和老人语音通话')
        .onClick((): void => { softTap(); this.toggleCall(); })
      }.width('100%').height('100%').backgroundColor(this.palette().backdrop)
    }.hideTitleBar(true).backgroundColor(this.palette().backdrop)
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
      .onReady((context: NavDestinationContext): void => { this.pathStack = context.pathStack; })
      .onShown((): void => { ThemeManager.getInstance().updateSystemUI(true); })
  }
}
