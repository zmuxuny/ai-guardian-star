// 跳转页面入口函数
@Builder
export function QRCodeCardBuilder() {
  QRCodeCard();
}

@Component
export struct QRCodeCard {
  pathStack: NavPathStack = new NavPathStack();
  
  build() {
    NavDestination() {
      Column() {
        // 导航栏
        Row() {
          Blank()
          
          Text('二维码名片')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
          
          Blank()
        }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 16 })
      .alignItems(VerticalAlign.Center)
      .backgroundColor(Color.White)

      // 二维码显示区域
      Column() {
        Text('我的二维码名片')
          .fontSize(18)
          .fontWeight(FontWeight.Bold)
          .fontColor(Color.Black)
          .margin({ bottom: 30 })

        // 二维码容器
        Column() {
          Image($r('app.media.qrcode'))
            .width(200)
            .height(200)
            .backgroundColor(Color.White)
            .fillColor(Color.Black)
            .borderRadius(12)
            .padding(20)

          Text('张三')
            .fontSize(16)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
            .margin({ top: 16 })

          Text('微信号: zhangsan1900')
            .fontSize(14)
            .fontColor('#666666')
            .margin({ top: 8 })
        }
        .backgroundColor(Color.White)
        .borderRadius(16)
        .padding({
          top: 30,
          bottom: 30,
          left: 20,
          right: 20
        })
        .shadow({
          radius: 8,
          color: '#00000020',
          offsetX: 0,
          offsetY: 2
        })

        Text('扫一扫上面的二维码，加我微信')
          .fontSize(14)
          .fontColor('#999999')
          .margin({ top: 20 })
      }
      .width('100%')
      .padding({ top: 40, bottom: 40 })
      .alignItems(HorizontalAlign.Center)
      .backgroundColor('#F2F2F7')

      Blank()
    }
      .width('100%')
      .height('100%')
      .backgroundColor('#F2F2F7')
      .expandSafeArea([SafeAreaType.SYSTEM], [SafeAreaEdge.TOP, SafeAreaEdge.BOTTOM])
    }
    .onReady((context: NavDestinationContext) => {
      this.pathStack = context.pathStack;
    })
  }
}
