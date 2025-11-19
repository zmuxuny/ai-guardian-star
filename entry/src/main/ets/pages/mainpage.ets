import { MqttManager } from './MqttManager';
import { ThemeManager } from '../common/ThemeManager';
// 【关键修正 1】导入 webview 模块
import webview from '@ohos.web.webview';

@Entry
@Component
export struct mainPage {
  @State selectedView: string = '正面视角';
  private volumeLevel: number = 50;
//altas 200I DK ip:192.168.137.100   web_ip:192.168.137.100:5000/     MQTT_ip:192.168.137.100:1883/
  // 【!!! 重要配置: 替换为您开发板的实际 IP 地址 !!!】
  @State videoUrl: string = 'http://192.168.137.100:5000/video_feed';

  // 使用可观察对象，确保 UI 随 MQTT 状态联动
  @State mqttManager: MqttManager = MqttManager.getInstance();
  @State themeManager: ThemeManager = ThemeManager.getInstance();
  
  // 本地状态变量，用于确保 UI 及时刷新
  @State isConnected: boolean = false;
  @State latestMessage: string = '正在初始化...';
  @State isFallDetected: boolean = false; // 本地摔倒状态
  private updateTimer: number = -1;

  // 【关键修正 2】将 WebController 更改为 WebviewController
  private webController: webview.WebviewController = new webview.WebviewController();

  aboutToAppear() {
    // 页面出现时进行连接与订阅
    this.mqttManager.connectAndSubscribe();
    console.info('[mqtt] mainpage MQTT 初始化并尝试连接');
    
    // 立即同步一次状态
    this.syncState();
    
    // 启动定时器，定期同步 MQTT 状态到本地状态
    // 使用较短的间隔确保摔倒状态能及时刷新
    this.startStateSync();
  }
  
  aboutToDisappear() {
    // 清理定时器
    if (this.updateTimer !== -1) {
      clearInterval(this.updateTimer);
      this.updateTimer = -1;
    }
  }
  
  // 同步状态方法
  private syncState() {
    let stateChanged: boolean = false;
    
    if (this.isConnected !== this.mqttManager.isConnected) {
      console.log(`[mainpage]:连接状态变化 ${this.isConnected} -> ${this.mqttManager.isConnected}`);
      this.isConnected = this.mqttManager.isConnected;
      stateChanged = true;
    }
    
    if (this.latestMessage !== this.mqttManager.latestMessage) {
      console.log(`[mainpage]:消息变化 "${this.latestMessage}" -> "${this.mqttManager.latestMessage}"`);
      this.latestMessage = this.mqttManager.latestMessage;
      stateChanged = true;
    }
    
    if (this.isFallDetected !== this.mqttManager.isFallDetected) {
      console.log(`[mainpage]:🔴 摔倒状态变化 ${this.isFallDetected} -> ${this.mqttManager.isFallDetected}`);
      this.isFallDetected = this.mqttManager.isFallDetected;
      stateChanged = true;
    }
    
    if (stateChanged) {
      console.log(`[mainpage]:状态已更新 isConnected=${this.isConnected}, isFallDetected=${this.isFallDetected}, message=${this.latestMessage.substring(0, 30)}...`);
    }
  }
  
  // 启动状态同步定时器
  private startStateSync() {
    // 每 100ms 检查一次状态变化，确保摔倒状态能及时刷新到 UI
    // 使用较短的间隔确保状态变化能快速反映
    this.updateTimer = setInterval(() => {
      this.syncState();
    }, 100) as number;
  }

  build() {
    Column() {
      // 标题栏
      Text('智能居家监护')
        .fontSize(20)
        .fontWeight(500)
        .width('100%')
        .margin({ left: 20, top: 20, bottom: 20 })
        .fontWeight(FontWeight.Bold)
        .fontColor(this.themeManager.colors.primaryTextColor)
        .alignSelf(ItemAlign.Start)

      // 视频流区域 (使用 Web 组件显示 MJPEG 流)
      Column() {
        Stack() {
          // 将 controller 传入 Web 组件
          Web({ src: this.videoUrl, controller: this.webController })
            .width('90%')
            .aspectRatio(16 / 9)
            .margin(10)
            .border({ radius: 8, color: this.themeManager.colors.borderColor, width: 1 })
        }
        .width('100%')

        Row() {
          Text(this.selectedView)
            .fontSize(16)
            .fontColor(this.themeManager.colors.primaryTextColor)
            .margin({ left: 10 })

          Blank()

          Button('!')
            .width(40)
            .height(40)
            .borderRadius(20)
            .backgroundColor(0xFFD81B60)
            .margin({ right: 10 })
        }
        .width('90%')
        .margin({ bottom: 10 })
      }
      .justifyContent(FlexAlign.Center)
      .width('100%')

      // 监控画面以下为可滚动区域
      Scroll() {
        Column() {
          // 设备连接状态 (显示 MQTT 状态)
          Row() {
            Image($r('app.media.img_3'))
              .width(20)
              .height(20)
            // 使用本地状态变量，确保 UI 及时刷新
            Text(this.isConnected ? '✅ MQTT已连接' : '❌ MQTT断开连接')
              .fontColor(this.isConnected ? Color.Green : Color.Red)
              .margin({ left: 8 })
            Text('   |   ')
            Image($r('app.media.img_4'))
              .width(20)
              .height(20)
            Text('网络正常')
              .fontColor(this.themeManager.colors.primaryTextColor)
              .margin({ left: 8 })
          }
          .justifyContent(FlexAlign.Center)
          .padding(5)
          .width('90%')
          .margin(10)
          .border({
            width: 1,
            color: this.themeManager.colors.borderColor,
            style: BorderStyle.Solid
          })

          // MQTT 消息显示区
          Text(this.latestMessage)
            .fontSize(18)
            .textAlign(TextAlign.Center)
            .width('90%')
            .backgroundColor(this.isFallDetected ? 
              (this.themeManager.isDarkMode ? '#4D1F1F' : '#FFE0E0') : 
              (this.themeManager.isDarkMode ? '#1F2D4D' : '#E6F7FF'))
            .fontColor(this.isFallDetected ? 
              this.themeManager.colors.dangerButtonColor : 
              this.themeManager.colors.primaryTextColor)
            .padding(12)
            .borderRadius(8)
            .margin(16)

          // 语音交互按钮
          Column() {
            Button({
              type: ButtonType.Circle,
            }) {
              Column() {
                Text('        ')
                Image($r('app.media.img_5'))
                  .width(24)
                  .height(24)
                  .margin({ bottom: 8 })
                Text('按住 说话')
                  .textAlign(TextAlign.Center)
                  .fontSize(16)
                  .fontColor(Color.White)
              }
              .width('100%')
              .height('100%')
            }
            .width(90)
            .height(90)
            .backgroundColor(0xFF1890FF)
            .borderRadius(60)
            .onClick(() => {
              console.info('输入语音');
            })
          }
          .width('100%')
          .margin({ bottom: 10 })

          Row() {
            Image($r('app.media.img_6'))
              .width(30)
              .height(30)
            Slider({
              value: this.volumeLevel,
              min: 0,
              max: 100
            })
              .onChange((value: number) => {
                this.volumeLevel = value;
              })
              .layoutWeight(1)
              .width(150)
              .margin({ left: 8 })
              .showTips(false)
          }
          .width('90%')
          .height(50)
          .padding(12)
          .backgroundColor(this.themeManager.colors.cardBackgroundColor)
          .borderRadius(20)
        }
        .width('100%')
      }
      .width('100%')
      .layoutWeight(1)
      .scrollBar(BarState.Off)
      .edgeEffect(EdgeEffect.Spring)
    }
    .width('100%')
    .height('100%')
    .backgroundColor(this.themeManager.colors.backgroundColor)
    .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
  }
}