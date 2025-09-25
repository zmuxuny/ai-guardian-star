@Component
export struct mainPage {
  @State selectedView: string = '正面视角';
  private volumeLevel: number = 50;
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
      .padding(10) // 调整整个Row的内边距
      .backgroundColor(Color.White) // 设置Row的背景颜色

      // 监控画面区域

        Row() {
          Stack({ alignContent: Alignment.Center }) {
            Image($r('app.media.img_1')) // 这里假设你有一个占位图片资源，实际中可能是视频流等
              .width('100%')
              .aspectRatio(1)
              .backgroundColor(0xFFE0E0E0)

            Text('⬆') // 图片上的小图标，可根据需求调整
              .fontSize(24)

            Button('!')
              .width(40)
              .height(40)
              .borderRadius(20)
              .backgroundColor(0xFFD81B60) // 设置按钮背景颜色为红色
              .position({ x: '100%', y: '100%' }) // 定位按钮到右下角
              .translate({ x: -40, y: -40 }) // 调整按钮位置，使其完全显示在监控画面区域内
          }
          .width('90%')
        }
        .justifyContent(FlexAlign.Center)
        .padding({ left: 10, right: 10 })
        .width('100%')
        .margin(10)

        // 监控画面以下为可滚动区域
        Scroll() {
          Column() {
            // 设备状态提示
            Row() {
              Image($r('app.media.img_3'))
                .width(20)
                .height(20)
              Text('设备已连接')
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

            // 自动检测提示
            Text('自动检测：老人现在状态良好')
              .fontSize(18)
              .textAlign(TextAlign.Center)
              .width('90%')
              .backgroundColor(0xFFE6F7FF)
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
