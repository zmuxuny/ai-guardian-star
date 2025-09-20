// 跳转页面入口函数
@Builder
export function MyAddressBuilder() {
  MyAddress();
}

@Component
export struct MyAddress {
  pathStack: NavPathStack = new NavPathStack();
  
  build() {
    NavDestination() {
      Column() {
        // 导航栏
        Row() {
          Blank()
          
          Text('我的地址')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
          
          Blank()
          
          Text('添加')
            .fontSize(16)
            .fontColor('#007AFF')
            .onClick(() => {
              // 这里可以添加新增地址的逻辑
              console.log('添加新地址')
            })
        }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 16 })
      .alignItems(VerticalAlign.Center)
      .backgroundColor(Color.White)

      // 地址列表
      Column() {
        // 默认地址
        Column() {
          Row() {
            Text('张三')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor(Color.Black)

            Text('138****8888')
              .fontSize(14)
              .fontColor('#666666')
              .margin({ left: 12 })

            Blank()

            Text('默认')
              .fontSize(12)
              .fontColor('#FF6B35')
              .backgroundColor('#FFF2ED')
              .padding({
                left: 8,
                right: 8,
                top: 2,
                bottom: 2
              })
              .borderRadius(4)
          }
          .width('100%')
          .margin({ bottom: 8 })

          Text('北京市朝阳区三里屯街道工体北路8号院')
            .fontSize(14)
            .fontColor('#333333')
            .width('100%')
            .margin({ bottom: 12 })

          Row() {
            Blank()

            Text('编辑')
              .fontSize(14)
              .fontColor('#007AFF')
              .margin({ right: 16 })
              .onClick(() => {
                console.log('编辑地址')
              })

            Text('删除')
              .fontSize(14)
              .fontColor('#FF3B30')
              .onClick(() => {
                console.log('删除地址')
              })
          }
          .width('100%')
        }
        .width('100%')
        .padding(16)
        .backgroundColor(Color.White)
        .borderRadius(8)
        .margin({ bottom: 12 })

        // 其他地址
        Column() {
          Row() {
            Text('李四')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor(Color.Black)

            Text('139****9999')
              .fontSize(14)
              .fontColor('#666666')
              .margin({ left: 12 })

            Blank()
          }
          .width('100%')
          .margin({ bottom: 8 })

          Text('上海市浦东新区陆家嘴环路1000号')
            .fontSize(14)
            .fontColor('#333333')
            .width('100%')
            .margin({ bottom: 12 })

          Row() {
            Blank()

            Text('设为默认')
              .fontSize(14)
              .fontColor('#007AFF')
              .margin({ right: 16 })
              .onClick(() => {
                console.log('设为默认地址')
              })

            Text('编辑')
              .fontSize(14)
              .fontColor('#007AFF')
              .margin({ right: 16 })
              .onClick(() => {
                console.log('编辑地址')
              })

            Text('删除')
              .fontSize(14)
              .fontColor('#FF3B30')
              .onClick(() => {
                console.log('删除地址')
              })
          }
          .width('100%')
        }
        .width('100%')
        .padding(16)
        .backgroundColor(Color.White)
        .borderRadius(8)
      }
      .width('100%')
      .padding({ left: 16, right: 16, top: 20 })

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
