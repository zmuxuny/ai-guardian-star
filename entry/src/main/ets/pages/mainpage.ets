import { MqttManager } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
import webview from '@ohos.web.webview';
import display from '@ohos.display';
import { AudioTransferManager } from '../common/AudioTransferManager';
import { abilityAccessCtrl } from '@kit.AbilityKit';
import { common } from '@kit.AbilityKit';

@Entry
@Component
export struct mainPage {
  @State videoUrl: string = 'http://192.168.137.100:5000/video_feed';
  @State volumeLevel: number = 50;
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  @State isConnected: boolean = false;
  @State latestMessage: string = '正在初始化...';
  @State isFallDetected: boolean = false;
  @State isSedentaryDetected: boolean = false;
  @State isTalking: boolean = false;
  // LIVE 绿点动画状态
  @State dotScale: number = 1.0;
  @State dotGlowScale: number = 1.0;
  @State dotGlowOpacity: number = 0.5;
  // 通话按钮缩放
  @State btnScale: number = 1.0;
  // 顶部状态栏安全高度（由 EntryAbility 写入 AppStorage）
  @StorageProp('topSafeHeight') topSafeHeight: number = 48;

  private updateTimer: number = -1;
  private webController: webview.WebviewController = new webview.WebviewController();
  private audioManager: AudioTransferManager = AudioTransferManager.getInstance();
  private context: common.UIAbilityContext = getContext(this) as common.UIAbilityContext;

  aboutToAppear(): void {
    this.mqttManager.connectAndSubscribe();
    this.syncState();
    this.updateTimer = setInterval(() => { this.syncState(); }, 100);
  }
  aboutToDisappear(): void {
    if (this.updateTimer !== -1) { clearInterval(this.updateTimer); this.updateTimer = -1; }
  }
  private syncState(): void {
    if (this.mqttManager) {
      this.isConnected = this.mqttManager.isConnected;
      this.latestMessage = this.mqttManager.latestMessage;
      this.isFallDetected = this.mqttManager.isFallDetected;
      this.isSedentaryDetected = this.mqttManager.isSedentaryDetected;
    }
  }

  @Builder
  GradientHeader(): void {
    Column() {
      Row() {
        Column() {
          Text('Guardian').fontSize(26).fontWeight(FontWeight.Bold).fontColor('#ffffff')
          Text('AI 实时监护').fontSize(13).fontColor('#B3FFFFFF').margin({ top: 4 })
        }.alignItems(HorizontalAlign.Start)
        Blank()
        // LIVE 角标：外圈光晕 + 内圈实心绿点
        Row() {
          Stack() {
            // 外圈呼吸光晕
            Circle({ width: 18, height: 18 })
              .fill('#10b981')
              .opacity(this.dotGlowOpacity)
              .scale({ x: this.dotGlowScale, y: this.dotGlowScale })
              .animation({ duration: 1400, curve: Curve.EaseInOut, iterations: -1, playMode: PlayMode.Alternate })
              .onAppear(() => { this.dotGlowScale = 1.8; this.dotGlowOpacity = 0.0; })
            // 内圈实心点
            Circle({ width: 9, height: 9 })
              .fill('#10b981')
              .scale({ x: this.dotScale, y: this.dotScale })
              .animation({ duration: 1000, curve: Curve.EaseInOut, iterations: -1, playMode: PlayMode.Alternate })
              .onAppear(() => { this.dotScale = 1.2; })
          }.width(18).height(18).margin({ right: 6 })
          Text('LIVE').fontSize(12).fontColor('#ffffff').fontWeight(FontWeight.Bold)
        }
        .padding({ left: '3%', right: '3%', top: '1.5%', bottom: '1.5%' })
        .backgroundColor('rgba(255,255,255,0.2)')
        .backgroundBlurStyle(BlurStyle.Thin)
        .borderRadius(100)
      }
      // top: 状态栏高度 + 内容间距；bottom 固定让两页 Header 等高
      .width('100%').padding({ left: '6%', right: '6%',  top: this.topSafeHeight + 16, bottom: 20 })
    }
    .width('100%')
    .linearGradient({ direction: GradientDirection.Bottom,
      colors: [['#1e40af', 0.0], ['#3b82f6', 0.5], ['#60a5fa', 1.0]] })
    .borderRadius({ bottomLeft: '6%', bottomRight: '6%' })
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP])
  }


  @Builder
  VideoArea(): void {
    Stack({ alignContent: Alignment.BottomEnd }) {
      if (this.isConnected) {
        Web({ src: this.videoUrl, controller: this.webController })
          .width('100%').aspectRatio(16 / 9).borderRadius('4%')
      } else {
        Column() {
          Image($r('app.media.ic_camera_off')).width('13%').aspectRatio(1).objectFit(ImageFit.Contain)
            .opacity(0.5)
          Text('摄像头未连接').fontSize(14).fontColor('#64748b').margin({ top: '3%' })
        }
        .width('100%').aspectRatio(16 / 9).justifyContent(FlexAlign.Center)
        .backgroundColor(this.themeManager.isDarkMode ? '#1a2744' : '#1e293b')
        .border({
          width: 1,
          color: this.themeManager.isDarkMode ? '#2d4a7a' : '#334155'
        })
        .borderRadius('4%')
      }
      if (!this.isConnected) {
        Row() {
          Image($r('app.media.ic_alert_white')).width(14).height(14).objectFit(ImageFit.Contain)
          Text('设备离线').fontSize(11).fontColor('#ffffff').margin({ left: 4 })
        }
        .padding({ left: '2.5%', right: '2.5%', top: '1%', bottom: '1%' })
        .backgroundColor('#ef4444').borderRadius(100)
        .margin({ right: '3%', bottom: '3%' })
      }
    }
    .width('92%')
    .shadow({ radius: 16, color: this.themeManager.isDarkMode ? '#000000AA' : '#1A1e40af', offsetY: 6 })
    .border({
      width: 1,
      color: this.themeManager.isDarkMode ? '#2d4a7a' : 'transparent'
    })
    .borderRadius('4%')
    .margin({ top: '-4%' })
  }

  @Builder
  StatusCards(): void {
    Column({ space: 0 }) {
      // 设备状态卡
      Row() {
        Column() {
          Text('设备状态').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          Text(this.isConnected ? '在线' : '离线').fontSize(20).fontWeight(FontWeight.Bold)
            .fontColor(this.isConnected ? '#10b981' : '#ef4444').margin({ top: '2%' })
        }.alignItems(HorizontalAlign.Start).layoutWeight(1)
        Image(this.isConnected ? $r('app.media.ic_shield_green') : $r('app.media.ic_link_off_red'))
          .width(32).height(32).objectFit(ImageFit.Contain).padding(5)
          .backgroundColor(this.isConnected ? '#ecfdf5' : '#fee2e2').borderRadius(10)
      }
      .width('100%').padding({ left: '5%', right: '5%', top: '4%', bottom: '4%' })
      .margin({ top: '3%' }).borderRadius('4%')
      .backgroundColor(this.isConnected
        ? this.themeManager.colors.cardBackgroundColor
        : (this.themeManager.isDarkMode ? '#2d1515' : '#fff5f5'))
      .border({ width: this.isConnected ? 0 : 1, color: this.themeManager.isDarkMode ? '#7f1d1d' : '#fecaca' })
      .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })

      // 监测状态卡
      Row() {
        Image($r('app.media.ic_shield_blue'))
          .width(32).height(32).objectFit(ImageFit.Contain).padding(5)
          .backgroundColor(this.themeManager.isDarkMode ? '#1e3a5f' : '#dbeafe').borderRadius(10)
        Column() {
          Text(this.isFallDetected ? '检测到跌倒' : '正常监测')
            .fontSize(16).fontWeight(FontWeight.Bold).fontColor(this.themeManager.colors.primaryTextColor)
          Text(this.latestMessage).fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
            .margin({ top: '2%' }).maxLines(1).textOverflow({ overflow: TextOverflow.Ellipsis })
        }.alignItems(HorizontalAlign.Start).margin({ left: '4%' }).layoutWeight(1)
        Circle({ width: '2%', height: '2%' }).fill('#f59e0b').aspectRatio(1)
      }
      .width('100%').padding({ left: '5%', right: '5%', top: '4%', bottom: '4%' })
      .margin({ top: '4%' }).borderRadius('4%')
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })

      // 音量卡
      Column() {
        Row() {
          Text('通话音量').fontSize(12).fontColor(this.themeManager.colors.secondaryTextColor)
          Blank()
          Text(`${Math.floor(this.volumeLevel)}%`).fontSize(12).fontWeight(FontWeight.Bold)
            .fontColor(this.themeManager.colors.primaryTextColor)
        }.width('100%').margin({ bottom: '3%' })
        Slider({ value: this.volumeLevel, style: SliderStyle.InSet })
          .onChange((v: number): void => { this.volumeLevel = v })
          .width('100%').selectedColor('#2563eb')
          .trackColor(this.themeManager.isDarkMode ? '#334155' : '#f1f5f9')
          .blockColor('#ffffff')
      }
      .width('100%').padding({ left: '5%', right: '5%', top: '4%', bottom: '4%' })
      .margin({ top: '4%' }).borderRadius('4%')
      .backgroundColor(this.themeManager.colors.cardBackgroundColor)
      .shadow({ radius: 8, color: '#0000000F', offsetY: 4 })
    }
    .width('92%').margin({ top: '3%' })
  }


  build() {
    Column() {
      Scroll() {
        Column() {
          this.GradientHeader()
          Column() { this.VideoArea() }.width('100%').alignItems(HorizontalAlign.Center)
          Column() { this.StatusCards() }.width('100%').alignItems(HorizontalAlign.Center)
          Blank().height('14%')
        }.width('100%')
      }
      .layoutWeight(1).scrollBar(BarState.Off).edgeEffect(EdgeEffect.Spring)

      Button() {
        Row() {
          Image($r(this.isTalking ? 'app.media.ic_offcall' : 'app.media.ic_phone_white'))
            .width(22).height(22).objectFit(ImageFit.Contain).margin({ right: '3%' })
          Text(this.isTalking ? '结束通话' : '发起通话')
            .fontSize(16).fontWeight(FontWeight.Medium).fontColor('#ffffff')
        }.justifyContent(FlexAlign.Center)
      }
      .width('88%').height('7%').constraintSize({ minHeight: 50 })
      .linearGradient({
        direction: GradientDirection.Left,
        colors: this.isTalking
          ? [['#dc2626', 0.0], ['#ef4444', 1.0]]
          : [['#1e40af', 0.0], ['#3b82f6', 1.0]]
      })
      .borderRadius(100)
      .shadow({ radius: 16, color: this.isTalking ? '#ef444440' : '#3b82f640', offsetY: 8 })
      .scale({ x: this.btnScale, y: this.btnScale })
      .animation({ duration: 150, curve: Curve.EaseInOut })
      .margin({ bottom: '4%', top: '2%' })
      .onClick(async (): Promise<void> => {
        this.btnScale = 0.93;
        setTimeout(() => { this.btnScale = 1.0; }, 150);
        if (this.isTalking) {
          await this.audioManager.stopCall(); this.isTalking = false;
        } else {
          const atManager = abilityAccessCtrl.createAtManager();
          const res = await atManager.requestPermissionsFromUser(this.context, ['ohos.permission.MICROPHONE']);
          if (res.authResults[0] === 0) { await this.audioManager.startCall(); this.isTalking = true; }
        }
      })
    }
    .width('100%').height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    //.expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}
