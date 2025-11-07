import { MqttManager } from './MqttManager';
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

  // 【关键修正 2】将 WebController 更改为 WebviewController
  private webController: webview.WebviewController = new webview.WebviewController();

  aboutToAppear() {
    // 页面出现时进行连接与订阅
    this.mqttManager.connectAndSubscribe();
    console.info('[mqtt] mainpage MQTT 初始化并尝试连接');
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
        .alignSelf(ItemAlign.Start)

      //搜索框
      Row() {
        Stack({alignContent:Alignment.End}) {
          TextInput({ placeholder: '日期＋时间 (例:11.12 5:00)' })
            .placeholderColor('#817D83')
            .fontSize(16)
            .fontColor(Color.Black)
            .padding({ left: 16, right: 8 })
            .layoutWeight(1)

          Image($r('app.media.search'))
            .width(20)
            .fillColor(Color.Black)
            .height(20)
            .margin(10)
        }
      }
      .padding(10)
      .backgroundColor(Color.White)

      // 视频流区域 (使用 Web 组件显示 MJPEG 流)
      Column() {
        // 将 controller 传入 Web 组件
        Web({ src: this.videoUrl, controller: this.webController })
          .width('90%')
          .aspectRatio(16/9)
          .margin(10)
          .border({ radius: 8, color: Color.Black, width: 1 })

        Row() {
          Text(this.selectedView)
            .fontSize(16)
            .fontColor(Color.Black)
            .margin({left: 10})

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
            // 根据 mqttManager 的状态显示不同的 UI
            Text(this.mqttManager.isConnected ? '✅ MQTT已连接' : '❌ MQTT断开连接')
              .fontColor(this.mqttManager.isConnected ? Color.Green : Color.Red)
              .margin({ left: 8 })
            Text('   |   ')
            Image($r('app.media.img_4'))
              .width(20)
              .height(20)
            Text('网络正常')
              .margin({ left: 8 })
          }
          .justifyContent(FlexAlign.Center)
          .padding(5)
          .width('90%')
          .margin(10)
          .border({
            width: 1,
            color: Color.Grey,
            style: BorderStyle.Solid
          })

          // MQTT 消息显示区
          Text(this.mqttManager.latestMessage)
            .fontSize(18)
            .textAlign(TextAlign.Center)
            .width('90%')
            .backgroundColor(this.mqttManager.latestMessage.includes('跌倒') ? 0xFFFFE0E0 : 0xFFE6F7FF)
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
                  .fontColor(Color.Black)
              }
              .width('100%')
              .height('100%')
            }
            .width(90)
            .height(90)
            .backgroundColor(0xFF1890FF)
            .borderRadius(60)
            .onClick(() => {
              console.info('按钮被点击，执行语音交互逻辑');
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
          .backgroundColor('#CCCCCC')
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
  }
}