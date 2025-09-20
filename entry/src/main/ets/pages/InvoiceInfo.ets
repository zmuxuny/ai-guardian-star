// 跳转页面入口函数
@Builder
export function InvoiceInfoBuilder() {
  InvoiceInfo();
}

@Component
export struct InvoiceInfo {
  pathStack: NavPathStack = new NavPathStack();
  
  build() {
    NavDestination() {
      Column() {
        // 导航栏
        Row() {
          Blank()
          
          Text('我的发票抬头')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .fontColor(Color.Black)
          
          Blank()
          
          Text('添加')
            .fontSize(16)
            .fontColor('#007AFF')
            .onClick(() => {
              // 这里可以添加新增发票抬头的逻辑
              console.log('添加新发票抬头')
            })
        }
      .width('100%')
      .height(56)
      .padding({ left: 16, right: 16 })
      .alignItems(VerticalAlign.Center)
      .backgroundColor(Color.White)

      // 发票抬头列表
      Column() {
        // 个人发票
        Column() {
          Row() {
            Text('个人')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor(Color.Black)

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

          Text('张三')
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
                console.log('编辑发票抬头')
              })

            Text('删除')
              .fontSize(14)
              .fontColor('#FF3B30')
              .onClick(() => {
                console.log('删除发票抬头')
              })
          }
          .width('100%')
        }
        .width('100%')
        .padding(16)
        .backgroundColor(Color.White)
        .borderRadius(8)
        .margin({ bottom: 12 })

        // 企业发票
        Column() {
          Row() {
            Text('企业')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .fontColor(Color.Black)

            Blank()
          }
          .width('100%')
          .margin({ bottom: 8 })

          Text('北京科技有限公司')
            .fontSize(14)
            .fontColor('#333333')
            .width('100%')
            .margin({ bottom: 4 })

          Text('统一社会信用代码: 91110000123456789X')
            .fontSize(12)
            .fontColor('#666666')
            .width('100%')
            .margin({ bottom: 12 })

          Row() {
            Blank()

            Text('设为默认')
              .fontSize(14)
              .fontColor('#007AFF')
              .margin({ right: 16 })
              .onClick(() => {
                console.log('设为默认发票抬头')
              })

            Text('编辑')
              .fontSize(14)
              .fontColor('#007AFF')
              .margin({ right: 16 })
              .onClick(() => {
                console.log('编辑发票抬头')
              })

            Text('删除')
              .fontSize(14)
              .fontColor('#FF3B30')
              .onClick(() => {
                console.log('删除发票抬头')
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
