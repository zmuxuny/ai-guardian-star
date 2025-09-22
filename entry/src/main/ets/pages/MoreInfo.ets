// 跳转页面入口函数
@Builder
export function MoreInfoBuilder() {
  MoreInfo();
}

@Component
export struct MoreInfo {
  pathStack: NavPathStack = new NavPathStack();
  
  build() {
    NavDestination() {
      Column() {
        // 导航栏
        Row() {
          Blank()
          
          Text('更多')
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

      // 更多信息内容
      Column() {
        // 性别
        Row() {
          Text('性别')
            .fontSize(16)
            .fontColor(Color.Black)

          Blank()

          Text('男')
            .fontSize(16)
            .fontColor(Color.Black)

          Text('>')
            .fontSize(16)
            .fontColor('#C7C7CC')
            .margin({ left: 8 })
        }
        .width('100%')
        .height(50)
        .padding({ left: 16, right: 16 })
        .justifyContent(FlexAlign.SpaceBetween)
        .alignItems(VerticalAlign.Center)
        .backgroundColor(Color.White)

        // 地区
        Row() {
          Text('地区')
            .fontSize(16)
            .fontColor(Color.Black)

          Blank()

          Text('北京 北京')
            .fontSize(16)
            .fontColor(Color.Black)

          Text('>')
            .fontSize(16)
            .fontColor('#C7C7CC')
            .margin({ left: 8 })
        }
        .width('100%')
        .height(50)
        .padding({ left: 16, right: 16 })
        .justifyContent(FlexAlign.SpaceBetween)
        .alignItems(VerticalAlign.Center)
        .backgroundColor(Color.White)

        // 个性签名
        Row() {
          Text('个性签名')
            .fontSize(16)
            .fontColor(Color.Black)

          Blank()

          Text('这个人很懒，什么都没留下')
            .fontSize(16)
            .fontColor(Color.Black)
            .maxLines(1)
            .textOverflow({ overflow: TextOverflow.Ellipsis })

          Text('>')
            .fontSize(16)
            .fontColor('#C7C7CC')
            .margin({ left: 8 })
        }
        .width('100%')
        .height(50)
        .padding({ left: 16, right: 16 })
        .justifyContent(FlexAlign.SpaceBetween)
        .alignItems(VerticalAlign.Center)
        .backgroundColor(Color.White)
      }
      .width('100%')
      .margin({ top: 20 })

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
