@Component
export struct mainPage {
  @State selectedView: string = '正面视角';
  private volumeLevel: number = 50;
  build() {

    Column() {

      // 标题栏
      Text('  智能居家监护')
        .fontSize(20)
        .fontWeight(500)
        .width('100%')
        .margin({ left: 10, top: 10, bottom: 10 })

      //搜索框
      Row() {
        TextInput({
          placeholder: '日期＋时间 (例:11.12 5:00)'
        })
          .placeholderColor('#817083')
          .padding({ left: 10 }) // 调整内边距以适应文本
          .fontColor('#817083') // 使用十六进制颜色代码以保持一致性
          .layoutWeight(1)
          .height(40) // 设置高度以匹配图像中的输入框高度
          .backgroundColor('#fff') // 设置背景颜色以匹配图像中的浅灰色
          .border({ width: 1, color: '#CCCCCC' }) // 添加边框以匹配图像

        Image($r('app.media.img')) // 替换为实际的图像资源
          .width(20)
          .height(20)
          .margin({ left: 8, right: 10 }) // 调整图像的边距
      }
      .padding(10) // 调整整个Row的内边距
      .backgroundColor('#FFFFFF') // 设置Row的背景颜色

      // 视角选择下拉框


      // 监控画面区域
      Row() {
        Stack({ alignContent: Alignment.Center }) {
          Image($r('app.media.img_1')) // 这里假设你有一个占位图片资源，实际中可能是视频流等
            .width('100%')
            .height(300)
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
      }
      .padding({ left: 10, right: 10 })
      .width('100%')
      .margin(10)


      // 设备状态提示
      Row() {
        Text('         ')
        Image($r('app.media.img_3')) // 假设有设备连接图标资源
          .width(20)
          .height(20)
        Text('设备已连接')
          .margin({ left: 8 })
        Text('   |   ')
        Image($r('app.media.img_4')) // 假设有WiFi正常图标资源
          .width(20)
          .height(20)
          .margin({ left: 16 })
        Text('网络正常')
          .margin({ left: 8 })
      }
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
        // 使用 Row 来实现图标和文字的水平排列（但图中是图标在上，文字在下，所以用 Column 更合适）
        // 改为 Column 包裹 Image 和 Text
        Button({
          type: ButtonType.Circle, }){
          // 使用 Column 来排列图标和文字
          Column() {
            Text('        ')
            // 麦克风图标
            Image($r('app.media.img_5')) // 替换为实际的麦克风图标资源
              .width(24)
              .height(24)
              .margin({ bottom: 8 }) // 图标和文字之间的间距

            // "按住 说话" 文字
            Text('按住 说话')
              .textAlign(TextAlign.Center)
              .fontSize(16)
              .fontColor(Color.Black)
          }
          .width('100%')
          .height('100%') // 增加高度以容纳图标和文字

        }
        .width(90)
        .height(90) // 按钮总高度
        .backgroundColor(0xFF1890FF)
        .borderRadius(60) // 圆形按钮，半径为宽度/高度的一半
        .onClick(() => {
          // 语音交互逻辑
          console.info('按钮被点击，执行语音交互逻辑');
        })
      }
      .width('100%')
      .margin({bottom:10})

      Row() {

            Image($r('app.media.img_6'))
            .width(30)
            .height(30)


        // 右侧音量滑动条
        Slider({
          value: this.volumeLevel,
          min: 0,
          max: 100
        })
          .onChange((value: number) => {
            this.volumeLevel = value; // 更新音量值
          })
          .layoutWeight(1)
          .width(150)
          .margin({ left: 8 }) // 与图标的间距
          .showTips(false) // 可选：隐藏滑动条的提示气泡

      }
      .width('90%')
      .height(50)
      .padding(12) // 内边距
      .backgroundColor('#CCCCCC') // 灰色背景，带透明度
      .borderRadius(20) // 圆角

      // Row() {
      //
      //   Button(this.isMuted ? '🔇' : '🔈') // 静音和音量图标切换
      //     .width(40)
      //     .height(40)
      //     .onClick(() => {
      //       this.isMuted = !this.isMuted;
      //     })
      //
      //   Slider({
      //     value: this.volumeLevel,
      //     min: 0,
      //     max: 100
      //   })
      //     .onChange((value: number) => {
      //       this.volumeLevel = value;
      //     })
      //     .width(150)
      //     .margin({ left: 16 })
      //
      //
      //
      // }
      // .margin({ left: 16, right: 16, bottom: 16 })
    }

  }
}
